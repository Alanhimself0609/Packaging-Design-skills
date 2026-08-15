# Packaging Design Skills

面向真实商业包装项目的 Codex Skill。核心能力包括低成本包装定位、设计费与订单定金关卡、五层方案生成、已确认效果图的高保真反向分层、Photoshop 2023 离线分层、字体授权、刀模与印前交接。

## 安装

将 `design-packaging` 文件夹复制到个人 Codex skills 目录：

```text
~/.codex/skills/design-packaging
```

调用示例：

```text
Use $design-packaging to reconstruct this approved packaging image into a high-fidelity layered concept PSD.
```

## 关键交付

- 五个固定顶层组：`01_BG`、`02_MAIN`、`03_AUX`、`04_LABEL`、`05_TYPE`
- 正向设计采用“先方案、快速预分层、真实叠加效果图、确认后按需精分层”；首轮保证至少 90% 重组相似度，不追求无意义的层数
- 需要独立调整的重要元素优先独立；容易后拆的小装饰可先合并并标记 `deferred_split`
- 原像素优先、遮挡区域局部补全、逐元素来源与可信度记录
- Photoshop 2023 离线分层 PSD、元素清单和还原报告
- 非背景元素可用透明 PNG，也可用“完整像素层 + 黑白蒙版”，不强制为透明而破坏边缘
- 自动装配脚本保留为可选能力，当前交付以分层准确为准
- 无真实尺寸、印刷方式、纸张和印厂参数时，只标记为高清概念稿

## 版本

当前版本：v1.0.0

扁平图片中完全被遮挡的像素无法被精确恢复，只能根据上下文合理补全；任何补全区域都会在还原报告中明确标记。
