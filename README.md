# tolstack

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

公差链（尺寸链）叠加分析工具：对装配封闭尺寸同时给出**极值法（Worst Case）**、**RSS 统计法（Root Sum Square）**和**蒙特卡洛模拟**三种结果，并按方差贡献与极值贡献对各组成环排序，帮助定位最值得收紧公差的环节。既有命令行工具，也有可导入的 Python API；纯标准库实现，无第三方运行时依赖。

[English](#english)

## 安装

```bash
pip install git+https://github.com/aoyexiaoqi/tolstack.git
```

从源码安装：

```bash
git clone https://github.com/aoyexiaoqi/tolstack.git
cd tolstack
pip install .
```

需要 Python 3.9 及以上版本。安装后命令名为 `tolstack`，也可以用 `python -m tolstack` 调用。

## 输入格式

一个尺寸链由若干**组成环（link）**构成，每个组成环包含：

| 字段 | 含义 |
|---|---|
| `name` | 环的名称 |
| `nominal` | 基本尺寸（标称值） |
| `tol_plus` | 上偏差的绝对值（≥ 0） |
| `tol_minus` | 下偏差的绝对值（≥ 0），省略时等于 `tol_plus`（对称公差） |
| `sign` | 方向：`+1` 增环 / `-1` 减环，省略时为 `+1` |

封闭环尺寸 = Σ（sign × 组成环尺寸）。

### JSON（完整示例）

```json
{
  "links": [
    {"name": "housing_depth",  "nominal": 50.0, "tol_plus": 0.10, "tol_minus": 0.10, "sign": 1},
    {"name": "shaft_shoulder", "nominal": 30.0, "tol_plus": 0.05, "tol_minus": 0.05, "sign": -1},
    {"name": "bearing_width",  "nominal": 19.0, "tol_plus": 0.04, "tol_minus": 0.04, "sign": -1}
  ]
}
```

也接受顶层直接是数组的写法（`[{...}, {...}]`）。仓库 `examples/gap_chain.json` 就是这个例子：壳体深度 50 − 轴肩 30 − 轴承宽 19 = 名义间隙 1.00。

### CSV

表头必填 `name,nominal,tol_plus`，`tol_minus` 与 `sign` 两列可整列省略（同上取默认值）：

```csv
name,nominal,tol_plus,tol_minus,sign
housing_depth,50.0,0.10,0.10,1
shaft_shoulder,30.0,0.05,0.05,-1
bearing_width,19.0,0.04,0.04,-1
```

见 `examples/gap_chain.csv`（与 JSON 例描述同一条链）。

## 用法（CLI）

```bash
tolstack analyze examples/gap_chain.json --spec-min 0.75 --spec-max 1.25
```

```text
Dimension chain: 3 link(s)
  housing_depth    nominal    50.0000 +0.1000/-0.1000  sign +1
  shaft_shoulder   nominal    30.0000 +0.0500/-0.0500  sign -1
  bearing_width    nominal    19.0000 +0.0400/-0.0400  sign -1

Closed dimension (nominal): 1.0000

Worst case (extreme value):
  Range:        [0.8100, 1.1900]
  Deviations:   +0.1900 / -0.1900  (total tolerance 0.3800)

RSS (root sum square, +/-3 sigma model):
  Mean:         1.0000   sigma: 0.0396
  +/-3 sigma:   [0.8813, 1.1187]  (total tolerance 0.2375)

Monte Carlo (n=10000, seed=42):
  Mean:         0.9999   std: 0.0396
  Range:        [0.8412, 1.1578]
  Percentiles:  P1 0.9075  P5 0.9343  P50 1.0005  P95 1.0652  P99 1.0917
  Spec [0.7500, 1.2500]: out-of-spec 0.0000% (0 ppm)

Contributions (ranked by variance share):
  #   link                variance %  worst-case %
  1   housing_depth            70.92         52.63
  2   shaft_shoulder           17.73         26.32
  3   bearing_width            11.35         21.05
```

选项：

- `--spec-min X` / `--spec-max Y`：封闭环的规格下限 / 上限，给出后蒙特卡洛会估算超差率（% 与 ppm）。可只给一侧。
- `--mc N`：蒙特卡洛采样数（默认 10000）。
- `--seed S`：随机种子（默认 42），固定种子保证结果可复现。
- `--json`：输出机器可读的完整 JSON 结果（各环定义、最差情况、RSS、蒙特卡洛、贡献度）。

## 用法（Python API）

```python
from tolstack import Chain, Link, analyze

chain = Chain([
    Link("housing_depth", 50.0, 0.10),            # tol_minus 省略 = 对称公差
    Link("shaft_shoulder", 30.0, 0.05, sign=-1),  # 减环
    Link("bearing_width", 19.0, 0.04, sign=-1),
])

result = analyze(chain, spec_min=0.75, spec_max=1.25, mc_samples=100_000, seed=42)
print(result.worst_case.minimum, result.worst_case.maximum)  # 0.81 1.19
print(result.rss.sigma)                                      # 0.0396
print(result.monte_carlo.out_of_spec_ppm)                    # 模拟超差 ppm
print(result.contributions[0].name)                          # 贡献最大的环

from tolstack import load_chain
chain = load_chain("examples/gap_chain.json")  # 或 .csv
```

单独调用也可以：`worst_case(chain)`、`rss(chain)`、`monte_carlo(chain, ...)`、`contributions(chain)`。

## 计算方法与假设

设组成环实际尺寸在其公差带内变动，封闭环 X = Σ signᵢ·xᵢ：

1. **极值法（Worst Case）**：所有环同时取到使封闭环最大 / 最小的极端值，保证 100% 互换性。封闭环总公差 = Σ（tol_plusᵢ + tol_minusᵢ）。
2. **RSS 法**：把每个环的公差带看作正态分布的 **±3σ 区间**，中心取公差带中点，即均值 μᵢ = nominal + (tol_plus − tol_minus)/2、σᵢ = (tol_plus + tol_minus)/2/3。封闭环 σ = √(Σσᵢ²)，±3σ 总公差 = √(Σ（tol_plusᵢ + tol_minusᵢ)²)。
3. **蒙特卡洛**：按与 RSS 完全相同的正态模型抽样（`tolstack` 默认种子 42），统计均值、标准差、P1/P5/P50/P95/P99 分位数，并按给定规格限估算超差率。因此样本足够大时蒙特卡洛的均值 / 标准差会收敛到 RSS 结果——可用它交叉验证 RSS。
4. **贡献度**：方差贡献 = σᵢ² / Σσ²（决定统计散布的主导环），极值贡献 =（tol_plusᵢ + tol_minusᵢ)/Σ（tol_plus + tol_minus）（决定极值法总公差的主导环），按方差贡献降序排列。

注意：±3σ 假设意味着默认各环工序能力约对应 Cpk≈1 且分布居中；若实际工艺有系统偏移或分布非正态，统计法结果会偏乐观，重要场合请以极值法兜底或用实测分布复核。

## 开发

```bash
pip install -e ".[test]"
pytest --cov=tolstack
```

## 许可

MIT，见 [LICENSE](LICENSE)。

---

## English

**tolstack** is a tolerance stack-up (dimension chain) analysis tool. For one closed (resulting) dimension it reports three complementary results — **worst case (extreme value)**, **RSS (root sum square)** and **Monte Carlo simulation** — plus a per-link contribution ranking (variance share and worst-case share) so you can see which link's tolerance is worth tightening first. It works both as a CLI (`tolstack analyze chain.json`) and as an importable Python package, uses only the standard library, and runs on Python 3.9+.

**Input**: a JSON file (object with a `links` list, or a bare list) or a CSV file with columns `name,nominal,tol_plus,tol_minus,sign`. Each link has a nominal size, upper/lower deviation magnitudes (`tol_minus` defaults to `tol_plus`, `sign` defaults to `+1` for an increasing link, `-1` for a decreasing one). The closed dimension is Σ(sign × link size).

**Model assumption**: for RSS and Monte Carlo, each link's tolerance band is treated as the ±3σ interval of a normal distribution centred on the band midpoint, i.e. σᵢ = (tol_plus + tol_minus)/2/3. Monte Carlo therefore converges to the RSS mean/σ for large sample counts, which makes the two methods cross-checkable. The CLI accepts `--spec-min/--spec-max` (closed-dimension spec limits for the Monte Carlo out-of-spec rate in % and ppm), `--mc N`, `--seed S` (default 42, reproducible) and `--json` for machine-readable output.

```bash
tolstack analyze examples/gap_chain.json --spec-min 0.75 --spec-max 1.25
```

See the Chinese section above for a full worked example with output, the formulas, and the Python API.

**License**: MIT.
