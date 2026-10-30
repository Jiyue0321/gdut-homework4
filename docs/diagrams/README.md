# 图表说明与重新渲染

腾讯文档**不支持** Mermaid 语法，所以这里的图都提前渲染成了 PNG。
把 PNG 直接拖进腾讯文档即可，不要粘贴 `.mmd` 里的代码。

## 现有图片

| 文件 | 内容 | 用在哪 |
| --- | --- | --- |
| `01-user-journey.png` | 用户旅程思维导图 | 需求文档 3.1、PPT「业务流程」页 |
| `02-feature-tree.png` | 功能分解思维导图 | 需求文档 3.2、PPT「功能概览」页 |
| `03-tech-stack.png` | 技术栈思维导图 | 需求文档 3.3、PPT「技术选型」页 |
| `04a-class-orchestration.png` | 编排与智能体类图 | 需求文档 8.1.1、答辩「架构」页 |
| `04b-class-data.png` | 数据模型类图 | 需求文档 8.1.2 |
| `05-state-machine.png` | 面试状态机 | 需求文档 8.2 |

对应的 `.mmd` 是可编辑的源文件；`.json` 是渲染配置（中文字体、主题）。

## 三种渲染方式

### 方式一：本地命令行（最省事，已配置好）

需要 Node.js（本机已有 v24）。在**项目根目录**执行：

```bash
npx -y @mermaid-js/mermaid-cli@latest \
  -i docs/diagrams/01-user-journey.mmd \
  -o docs/diagrams/01-user-journey.png \
  -b white \
  -c docs/diagrams/mermaid-config.json \
  -s 2
```

- `-b white` 白底，粘贴到白色文档里没有灰边
- `-c` 指定中文字体配置，不加会渲染出点阵字
- `-s 2` 两倍分辨率，网页缩小时仍清晰

批量重渲染全部图：

```bash
for f in docs/diagrams/*.mmd; do
  npx -y @mermaid-js/mermaid-cli@latest -i "$f" \
    -o "${f%.mmd}.png" -b white -c docs/diagrams/mermaid-config.json -s 2
done
```

单张约 20–60 秒，首次运行 `npx` 会下载依赖。

### 方式二：Mermaid Live Editor（改图最快）

打开 <https://mermaid.live> ，把 `.mmd` 文件内容粘进左侧编辑区，右侧实时预览，
点 **Actions → Download PNG** 下载。

适合临时调整节点文字。注意默认字体不含中文优化，导出前在左侧 Config 里加：

```json
{ "themeVariables": { "fontFamily": "Microsoft YaHei" } }
```

### 方式三：其他在线编辑器

| 工具 | 地址 | 说明 |
| --- | --- | --- |
| Mermaid Live | https://mermaid.live | 官方，支持全部图类型，可导出 SVG/PNG |
| Mermaid Chart | https://www.mermaidchart.com | 有免费额度，可协作编辑 |
| draw.io | https://app.diagrams.net | 不支持 Mermaid 导入（可通过 Mermaid 插件），但适合手工重画更精美的版本 |

**答辩 PPT 建议**：思维导图用 mermaid.live 导出 SVG（矢量，放大不糊），
类图用 `04a`/`04b` 的 PNG，投影时字号足够。

## 图为什么这样拆

- 类图原本一张 1568×2040，插进 A4 文档后字号小于 8pt 不可读，
  因此按「谁调用谁」和「存了什么数据」拆成两张；
- 状态机横向渲染会被压成一条 86px 高的细线（Mermaid 的已知表现），
  所以保持纵向；
- 思维导图刻意控制到三层，超过三层在文档里会挤成一团。
