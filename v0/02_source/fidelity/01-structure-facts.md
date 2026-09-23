# 01 — 结构层事实（STR）

- 作者：artisan（舰载工程官），M5.1 **r1.5**（L0 换锚）；设计 v3 §5.1 事实行语法（L0 口径 B）
- 事实行格式：`- [STR-NN] <一行事实> || anchor: ch<真章号> <官方URL> <首发时间> || src: sha256=9c8b562e94e0 lines=<a>-<b>`（可选尾部 ` || mirror: PASS(x%)`）
- **一级锚点 = L0 校对版全本**：`src:` 段的 sha256 前缀与行区间取自 `refs/original-source/L1-fulltext-index.tsv` 的同一行（`no` / `official_url` / `first_pub` / `src_line_start` / `src_line_end`），**不自行数行**
- 来源层：本册事实的**锚点与行区间**取自 L0 全本；事实文本沿用 r1 抽取（r1 内容取自 L2 镜像，镜像已降级为交叉校验）
- `mirror: PASS(x%)` 的语义 = **镜像正文长度在 ±12% 内**，**不代表内容已逐字核对**（见 `00` 册 §3.4）；本轮从 L0 补齐的事实不带镜像读数
- `UNVERIFIED` 只用于 L0 全本内确实找不到的事实，逐条给检索方式（见 `00` 册 §6）

- [STR-01] 主舞台是名为幸福小区的居民楼群，楼群由两栋并立的楼组成，正文分别称其为一号楼与二号楼 || anchor: ch75 https://www.qidian.com/chapter/1025901449/638543171/ 2021-03-03 12:42:14 || src: sha256=9c8b562e94e0 lines=3932-3987 || mirror: PASS(-10.8%)
- [STR-02] 楼体共十层，正文说明楼层数与游戏里一致 || anchor: ch71 https://www.qidian.com/chapter/1025901449/638323468/ 2021-03-01 21:52:11 || src: sha256=9c8b562e94e0 lines=3727-3774 || mirror: PASS(-10.0%)
- [STR-03] 房间号是四位数字；韩非的住处是 1044 号房间 || anchor: ch72 https://www.qidian.com/chapter/1025901449/638323629/ 2021-03-01 21:58:08 || src: sha256=9c8b562e94e0 lines=3776-3829 || mirror: PASS(-11.1%)
- [STR-04] 楼体陈旧破败，正文以破旧的老楼描述；老城区一带也保持多年前的破败样貌 || anchor: ch240 https://www.qidian.com/chapter/1025901449/651888068/ 2021-05-16 11:06:38 || src: sha256=9c8b562e94e0 lines=14248-14300 || mirror: PASS(-9.7%)
- [STR-05] 四楼有凶宅：魏有福夫妇被杀的凶宅位于四楼 || anchor: ch11 https://www.qidian.com/chapter/1025901449/632959828/ 2021-01-29 12:03:06 || src: sha256=9c8b562e94e0 lines=592-633 || mirror: PASS(-10.0%)
- [STR-06] 二号楼三层以下相对安全；徐琴曾前往二号楼取食材 || anchor: ch107 https://www.qidian.com/chapter/1025901449/641586215/ 2021-03-19 12:01:36 || src: sha256=9c8b562e94e0 lines=5768-5823 || mirror: PASS(-10.6%)
- [STR-07] 楼长以前的住处是十楼，他的房间也是楼内秘密的集中处 || anchor: ch61 https://www.qidian.com/chapter/1025901449/637123307/ 2021-02-24 20:54:19 || src: sha256=9c8b562e94e0 lines=3185-3235 || mirror: PASS(-10.4%)
- [STR-08] 十楼即楼顶，正文称这栋鬼楼的顶层出乎所有人预料 || anchor: ch98 https://www.qidian.com/chapter/1025901449/640685841/ 2021-03-14 18:00:00 || src: sha256=9c8b562e94e0 lines=5255-5301 || mirror: PASS(-10.1%)
- [STR-09] 幸福小区位于老城区、紧邻一处化工厂后方，现已荒废 || anchor: ch71 https://www.qidian.com/chapter/1025901449/638323468/ 2021-03-01 21:52:11 || src: sha256=9c8b562e94e0 lines=3727-3774 || mirror: PASS(-10.0%)
- [STR-10] 中庭（院落或天井）的形态与规模 || anchor: UNVERIFIED || reason: L0 全本内 0 命中（检索方式：逐词全书计数）——`中庭` 全书仅 1 处且属孤儿院语境（ch505），`天井` 0 处，`院落` 4 处（ch755/771/907/977）均为花园 / 公寓楼前语境 ⇒ 幸福小区中庭的形态与规模在 L0 全本内未取得
- [STR-11] 两栋楼之间的相互距离 || anchor: UNVERIFIED || reason: L0 全本内 0 命中（检索方式：逐词全书计数 + 同行共现）——`楼间距` 0 处；`相距` 4 处（ch22/174/182/495）均指其他对象；`两栋楼` 2 处（ch115/ch590）不含间距表述 ⇒ 该事实在 L0 全本内未取得
- [STR-12] 楼内房间编号的划分规则：房号首位数对应楼号，中间两位对应楼层，末位对应同层户序 || anchor: ch324 https://www.qidian.com/chapter/1025901449/658708690/ 2021-06-28 11:20:04 || src: sha256=9c8b562e94e0 lines=19473-19529
