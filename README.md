# dharmakit

佛教文献检索工具集，以 [Claude Code](https://claude.com/claude-code) 插件形式提供。

给做佛学研究、翻译、讲稿的人用：追一句藏文的出处、核一段汉文引文、取精确到册页行的引用锚点，这些事本来要在几个网站之间来回翻，现在可以直接问。

按数据源分成三个套件，**按需装，不必全装**。

## 安装

```
/plugin marketplace add dharmakit/skills
```

然后挑要的装：

```
/plugin install cbeta@dharmakit       # 汉文大藏经
/plugin install bdrc@dharmakit        # 藏文文献：书目检索、PDF 下载、OCR
/plugin install adarshah@dharmakit    # 藏文大藏经全文检索
```

---

## cbeta — 汉文大藏经

含两个技能。

### `cbeta` · 官方 API

走[法鼓文理学院](https://cbetaonline.dila.edu.tw/) CBETA 官方 API，免 key 免注册，装上即用。

> 「色不異空」这句在大正藏第几册第几页？

> 取《心經》T0251 卷一全文

> T1580 的译者是谁、几卷、什么年代？

学术引用需要的 `linehead` 锚点（形如 `T08n0251_p0848c07`，即册-经-页-栏-行）由它提供。

### `cbeta-local` · 本地全文检索（可选）

高频检索走本地，单次几毫秒，不联网。取整卷全文和书目元数据仍走上面的 API。

> 「色不異空」出自哪几部经？

> 确认 T1580 里没有「前九地是三乘境」这个判摄

每条结果自带**精确到行的引用锚点**：

```
[1] T1579 瑜伽師地論 卷1
    T30n1579_p0279a13
    五識相應、意、有尋伺等三、… 有依、及無依，是名【十七地】。
```

这个锚点由索引里的段内偏移算出，实测与 CBETA 官方 API 逐字一致，但不需要联网回查。

**经文数据不随插件分发**，自己去 [CBETA 官方仓库](https://github.com/cbeta-org/xml-p5)
clone，再用附带的 `cbeta_index.py` 建一次索引。建索引时校勘注会被排除、
校勘取底本读法——这两条决定了检索质量，细节在技能文档里。

---

## bdrc — 藏文文献

含三个技能，来自 [BDRC](https://library.bdrc.io)（佛教数字资源中心）。

### `bdrc-es` · 书目检索

搜全库的书目、篇目、人物，拿到可下载的 Instance MW 号。免注册、免 token。

> 「རྟེན་འབྲེལ་བསྟོད་པ་」这部在 BDRC 有哪些版本可下？

> 这篇短赞收在哪本合集里？

短篇愿赞、赞颂常常不作为独立条目存在，而是捆在 thor bu 合集中——
**Instance 层查无并不等于不存在**，本工具会顺着 PartTypeText 摸到母合集。
这是这类检索最常见的翻车点。

藏文输入需转 EWTS Wylie（靠 `pyewts`，装不上就直接传 Wylie）。

### `bdrc` · 文献下载

搜索并下载藏文佛典扫描本 PDF，支持单篇、搜索浏览、批量三种模式。

搜索浏览不需要 token；**下载 PDF 需要用户自己的 BDRC 账号 token**（从浏览器
localStorage 取，有效期约两小时）。请遵守 BDRC 的使用条款，只取标记为
open access 的资源，并节制请求频率——那是一家公益机构。

### `bdrc-ocr` · 藏文离线 OCR

用 BDRC 的开源模型识别藏文图片与扫描 PDF，现代印刷、木刻版、手写乌梅体各有对应模型。
完全本地运行，不联网。

> 把这本木刻版 PDF 的藏文提出来

需先自行安装上游 [`buda-base/tibetan-ocr-app`](https://github.com/buda-base/tibetan-ocr-app)（MIT）
并下载模型——本仓库只提供调用封装与流程，不附带模型和推理代码。
技能文档里记了上游 `cli.py` 一处会导致模型加载失败的坑。

---

## adarshah — 藏文大藏经

检索 [Adarshah](https://online.adarshah.org)（Dharma Treasure Corp）的语料，覆盖 14 个以上的库：

- **甘珠尔**：德格、江、拉萨、那塘、北京、托格、普扎、塔波
- **丹珠尔**：德格、北京
- **祖师文集**：宗喀巴、多罗那他、八世噶玛巴、果然巴、释迦确丹、萨迦诸祖、历代法王、《大宝伏藏》

> 查找藏文 `ཇི་སྙེད་སུ་དག་ཕྱོགས་བཅུའི་འཇིག་རྟེན་ན`

> 这句是原典直引还是后人改写？

> 这首颂在德格、江、拉萨三版甘珠尔各在什么位置？

站点免费开放，无需注册，无需 API key。附带的 CLI 只用 Python 标准库，没有依赖要装。

---

## 这些技能里写了什么

每个技能除了用法，还记着一批实测踩出来的坑，比如：

- Adarshah 后端的 `size` 硬编码 20，`searchAfter` 翻页会让 phrase 匹配失效——CLI 里绕开了
- CBETA 的 `/search/kwic` 缺 `juan` 参数时返回空结果**却不报错**，极易误判成「查无此句」
- 字面检索里标点和插字都会断词，所以断言「某经里没有某句」必须换 3–5 个词形交叉验证

这类判据比命令本身更值钱，写进技能是为了让模型别在同一个地方栽第二次。

## 引用规范

这几个工具面向学术使用，技能里对输出有一些约束：引用照抄数据源自带的 citation 格式，不自拟；数据里没有的字段不靠模型记忆补造；负向结论（「没有这句」）必须交叉验证过才能下。

## 数据来源与授权

本仓库只提供 API 客户端、脚本与使用说明，**不附带任何语料，也不附带 OCR 模型**。

- Adarshah 的 toolbox 页面标注 CC BY-NC-ND 4.0，取数据做研究与离线阅读没问题，商用或二次发布数据本身需另行确认
- CBETA 的授权见[官方说明](https://www.cbeta.org/copyright.php)
- BDRC 的资源各有访问级别，请只取标记为 open access 的
- 藏文 OCR 模型来自 [`buda-base/tibetan-ocr-app`](https://github.com/buda-base/tibetan-ocr-app)（MIT）

请遵守各数据源自己的使用条款，也请节制请求频率。

## 参与

欢迎提 issue 和 PR。比较有价值的几类：

- **踩到新的坑**——某个接口的参数陷阱、某种查询下的静默失败，这类实测经验最值得写进技能文档
- **补 Adarshah 的 kdb 代号**——现有清单不完整，从 `count` 输出的 buckets 里认出新代号就可以补
- **建索引的边缘情况**——CBETA 的 TEI 标记有不少特例，遇到解析异常的经欢迎报

**数据本身的问题请报给数据源**：经文有误、扫描本缺页、书目著录不对，属于 CBETA、BDRC、
Adarshah 各自的范围，报到这里我们也改不了。

## License

代码与文档采用 MIT，见 [LICENSE](LICENSE)。
