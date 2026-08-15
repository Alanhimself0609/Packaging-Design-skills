# 工具适配器

## 通用原则

核心流程不依赖某个生成模型。所有工具都必须输出可追溯素材、保持画布和坐标、记录提示词与来源，并通过元素清单和重组检查。

## OpenAI ImageGen

- 用于方向探索、单元素补全、局部高清重建和简单透明素材。
- 编辑时重复“只修改缺失区域，保持已批准像素不变”。
- 简单透明素材优先纯色键背景加本地去背；复杂透明边缘需要更严格的原生透明路径或人工蒙版。
- 每个不同元素分别生成，不用一张图同时生成多种独立素材。

## Adobe Firefly 与 Illustrator

- Firefly 可使用构图参考和风格参考控制一致性，但不能替代真实刀模和生产校验。
- Illustrator 的生成式矢量可作为重构起点；正式矢量必须人工清理节点、闭合路径、检查字形和最小线宽。
- 生成式扩展可辅助补出血，但必须与真实出血要求和原图边缘对照。
- Firefly 不可用或 Photoshop 离线时，回退到 ImageGen 加本地 Illustrator/Photoshop 人工重构。

## Photoshop 2023 离线分层

默认程序路径：`C:\Users\25111\Adobe Photoshop 2023\Photoshop.exe`。

1. 在命令行先运行 `validate_layer_package.py`。
2. 当前优先手工分层：创建五个顶层组，透明元素直接置入；不透明元素保留完整像素并加载对应黑白蒙版。
3. 自动化暂不作为交付条件。以后需要时，可在 Photoshop 中选择“文件 → 脚本 → 浏览”，打开 `assemble_concept_psd.jsx` 并选择 `element-manifest.json`。
4. 当前自动脚本只适用于 `transparent-png` 元素；包含 `layer-mask` 的项目必须手工装配，避免脚本忽略蒙版。
5. Photoshop 不需要登录或联网；手工分层和可选脚本都不调用生成式填充或云端服务。

## CorelDRAW

仅在订单定金后使用真实刀模制作生产文件。分离刀模、图形、文字、工艺和说明；使用授权矢量素材；按印厂要求设置 CMYK、专色、叠印和输出格式。

## 无 Photoshop 回退

可安装 `scripts/requirements.txt`，使用 `inspect_psd.py` 读取和检查 PSD 结构。第三方库只作复核，不替代 Photoshop 2023 的最终兼容性打开测试。
