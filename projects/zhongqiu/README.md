# 同一个节日，许多种动作

**状态：** 完整成片已制作并通过技术 QA。
**本地交付：** [`final.mp4`](final.mp4)（约 3 分 9 秒，1920×1080，24 fps，普通话旁白）
**审看图：** [`review.jpg`](review.jpg)

影片从骰子、火龙、烤肉、月饼和家庭分享切入，再解释农历八月十五、节日长期形成的过程、月饼文献证据的边界，以及厦门、香港、台湾、苏州和海外家庭各自不同的实践。结尾回到同一节日时间如何进入不同私人生活，不要求观众重复同一种习俗。

## 制作方式

- ImageGen 水彩与墨线画面构成插画纪录片场景。地名、日期、事实标签和中文字幕均在后期排版；匿名 composite 角色不复刻受访对象。
- Blender 5.2.1 CLI 刚体模拟制作六枚骰子落入瓷碗、碰撞和停稳的连续动作；其他插画使用 FFmpeg 做克制的纸面镜头运动，不把静帧平移说成真人动作。
- 普通话旁白来自本机 Microsoft System.Speech 离线合成。骰子、瓷器和酥皮使用 Freesound CC0 Foley；煎锅和街巷脚步使用 Mixkit 免费许可音效。器乐配乐为 Mixkit 免费许可曲目，并在结尾前淡出。
- 旧的来源不明烧烤/火龙鼓音频未进入成片。影片没有伪造现场广播、历史录音或受访者声音。

## 复现与 QA

在已有本地素材的环境中运行：

```powershell
python pipeline.py
```

管线渲染插画镜头、排字幕、装配 Blender 动作镜头、混合旁白/音乐/Foley，输出 H.264 视频、contact sheet 与 [技术 QA 报告](assets/final_qa.json)。逐段剪辑表和资产来源见 [edit_timeline.json](assets/edit_timeline.json) 与 [asset_manifest.json](assets/asset_manifest.json)；事实依据与不确定性边界见 [sources.md](sources.md)。

成片和大体积生成音频/视频保存在本地工作区并由 Git 忽略；代码、旁白文本、剪辑表、来源、manifest、QA 报告与审看图进入仓库。完整依赖和工具盘点见仓库根目录的 [hardware_report.json](../../hardware_report.json)。
