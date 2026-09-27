# 研究来源

本片只使用 OpenAI 的官方公告、研究文章和开发文档确认 GPT 相关技术事实。官方材料是技术节点的一手来源，但其中的能力评价和使用案例仍是发布方自述；影片不把它们当作独立评测或普通用户调查。

## 节点与来源

- [Improving language understanding with unsupervised learning](https://openai.com/index/language-unsupervised/)，OpenAI，2018-06-11。自监督预训练、Transformer、用自然语言建模信号学习后迁移到多种任务。片中作为“从大量文本开始”的结构起点；不呈现无来源的模型参数数字。
- [Language models are few-shot learners](https://openai.com/index/language-models-are-few-shot-learners/)，OpenAI，2020-05-28。GPT-3 的少样本任务演示将示例放进上下文，不需为每个示例更新梯度；报告了 1750 亿参数。片中重点表现“上下文变成操作界面”，不逐代报产品清单。
- [Introducing ChatGPT](https://openai.com/index/chatgpt/)，OpenAI，2022-11-30。对话格式能处理后续问题、承认错误、回应纠正；训练采用 RLHF 流程。公告中的代码修复等示例属于产品展示，不代表全部用户经历。
- [GPT-4](https://openai.com/index/gpt-4-research/)，OpenAI，2023-03-14。多模态研究系统接受图像/文本并输出文本；发布时图像输入仍处研究预览阶段。片中不暗示所有用户当日都能使用。
- [Function calling and other API updates](https://openai.com/index/function-calling-and-other-api-updates/)，OpenAI，2023-06-13。开发者可定义外部函数/API，模型输出结构化参数，由应用连接工具。工具执行不是语言模型单独完成。
- [Hello GPT-4o](https://openai.com/index/hello-gpt-4o/)，OpenAI，2024-05-13。官方描述 GPT-4o 可输入文字、音频、图像、视频的组合并产出文字、音频、图像；发布时各模态可用性并非同时完整开放。片中表现交互模态组合，不把产品上线情况写成“一次性完全开放”。
- [Learning to reason with LLMs](https://openai.com/index/learning-to-reason-with-llms/)，OpenAI，2024-09-12。o1 通过强化学习与测试时计算，使模型可在回答前投入更多推理时间；其性能数值是 OpenAI 对自身评估的报告，片中只采用“等待/思考时间成为结构”这一事实。
- [Introducing GPT-5](https://openai.com/index/introducing-gpt-5/)，OpenAI，2025-08-07。GPT-5 发布为统一系统，包括响应较快的模型、较深推理模型与实时路由机制；可与工具完成更复杂的端到端任务。片中不把官方性能描述当作作者结论。
- [Introducing GPT-5.3-Codex](https://openai.com/index/introducing-gpt-5-3-codex/)，OpenAI，2026-02-05。Codex 能延展到长时间研究、工具使用和复杂执行；案例是发布方说明的产品能力。
- [Introducing GPT-5.4](https://openai.com/index/introducing-gpt-5-4/)，OpenAI，2026-03-05。宣布面向 Codex/API 的原生计算机使用能力，可通过界面完成复杂工作流程；模型提出动作，执行由环境和调用系统承载。
- [GPT-6 Astra: A new generation of intelligence](https://openai.com/index/gpt-6-astra/)，OpenAI，2026-09-03。最新节点截至项目研究日（2026-09-28）；发布方称其结合计算机使用与多步工作，可产出文档、表格和演示。影片把“任务/交付物”作为观察对象，不复述基准或宣传性比较。

## 观察与边界

- **可验证事实**：预训练、few-shot/in-context、对话交互、多模态、API function calling、推理时计算、系统级路由及计算机界面工作流，分别见上述原始发布材料。
- **来源中的观点**：有关“更强”“专业级”“最聪明”等评价来自 OpenAI，不作为片中不加限定的事实。
- **作者观察**：重要变化不只是模型输出能力，而是用户愿意把工作的哪个边界交给系统。从一段文字到多步工作，人的动作逐渐由逐词输入转为设定目标、授权工具与审阅结果。
- **生活层材料边界**：片中“写代码的手、放入图像的手、允许工具动作的手”是把官方展示的用户/开发者任务转成可见的复合场景；不声称采访了某个真实用户，不把少数演示当成总体使用调查。
