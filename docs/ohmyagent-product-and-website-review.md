# OhMyAgent 产品与官网重构基础资料

> 调研日期：2026-09-04  
> 调研范围：`ohmyagent.ai` 官网、`studio.ohmyagent.ai` 实际工作区、项目 `/Users/scott/Documents/codes/opensource/pi-rpc-pydemo/`  
> 用途：作为后续官网信息架构、视觉设计、文案和案例内容的基础材料。  
> 说明：页面观察来自本次登录后的实际界面；技术能力来自仓库代码、README、设计规格和部署文档。没有把网页上的营销描述直接当成产品事实。

## 1. 一句话判断

OhMyAgent 的真正产品不是“一个在线聊天机器人”，也不是“一个普通的 coding agent 网页版”。它更接近：

> 面向企业的私有化 AI 工作系统，把模型、Agent 方法、工具、内部知识和执行流程组合起来，让企业把重复的知识工作变成可运行、可复用、可审计的 AI 工作流。

当前官网已经开始从“面向开发者的 Agent Platform”转向“面向业务工作的 Agent Platform”，但仍然存在明显错位：

- 首页强调 browser-based、non-coders、credits、免费/订阅套餐，容易让人理解成 SaaS 工具。
- 没有把“私有化部署、企业数据边界、模型自主选择、FDE 落地服务”放到核心叙事中心。
- Studio 的真实能力已经足够支撑一套企业 AI 落地方案，但官网没有把“为什么企业需要它、如何落地、交付什么结果”讲清楚。
- 官网有较完整的技术词汇和平台概念，却缺少客户决策需要的安全、部署、治理、服务和 ROI 证据。

## 2. 已确认的产品能力

### 2.1 Studio 工作区

登录后可见的主导航为：

1. New chat
2. Agents
3. Autopilots
4. Marketplace
5. Library
6. Settings

左侧长期保留 Chat history，可搜索历史会话；底部提供 Settings 和 Log out。

### 2.2 在线创建和管理 Agent

Agents 页面可以创建、编辑、删除、分享 Agent，Agent 卡片展示头像、名称、指令摘要和已使用的聊天数量。

Agent 编辑面板已确认包含：

- Agent name
- Provider
- Model
- Thinking effort
- Instruction
- Built-in tools
- Extensions
- Skills
- MCP servers

当前实际示例中，Provider 可见 `deepseek`、`sensenova`、`omlx`、`Zhipu GLM`；模型和推理强度根据 Provider/模型目录动态呈现。Agent 可以选择 `read`、`write`、`edit`、`bash`、`grep`、`find`、`ls`、`web_fetch`、`web_search` 等内置工具。

这意味着产品的核心价值不是“给每个人一个聊天窗口”，而是让组织把一个角色、方法、权限和能力集合封装成可复用的数字员工。

### 2.3 Skill、Extension、MCP 的组合式能力

Marketplace 页面已确认有以下资源类型：

- Skills
- Extensions
- MCP Servers
- Agents
- Agent Teams（当前页面提示尚无共享 Agent Teams）

Skills 既能浏览工作区已有资源，也能通过 skills.sh 搜索、预览、安装和卸载。Extensions 支持按 npm 包安装和卸载。MCP Servers 当前以工作区发现结果为主。

Agent 配置时需要显式勾选资源，发现资源不等于自动启用。这个设计很重要，适合未来官网表达为“能力可组合，权限可控”，而不是简单地罗列生态数量。

### 2.4 在线使用和流式执行

New chat 选择一个 Agent 后发起会话。一个 Chat 固定绑定一个 Agent，首条消息发出后不能切换 Agent。会话支持：

- 流式输出
- Markdown、代码块、表格、列表
- Thinking 和工具活动展示
- 工具结果折叠
- 会话标题编辑
- 会话历史恢复
- Abort/中止运行
- 从会话查看生成文件
- 分享会话

实际历史会话中已经出现研究、跨境电商、标准化、TikTok 等工作任务，说明产品已有真实的知识工作使用痕迹。

### 2.5 Autopilots：定时或手动运行

Autopilots 页面可以创建、搜索、编辑、删除自动化任务，也可以：

- 启用/停用任务
- Run now
- 查看运行历史
- 关联产生的 Chat 会话
- 按 cron 规则调度
- 设置开始和结束时间

它的客户价值不是“定时发消息”，而是把一次性 Prompt 升级为持续运行的业务流程，例如每日情报、周期性竞品监测、日报周报、内容生产或合规检查。

### 2.6 Library：结果资产沉淀

Library 页面聚合 Agent 创建的文件，支持：

- 按 Agent 筛选
- 文件名搜索
- 分页
- 打开文件
- 下载文件
- 回看来源 Chat

实际数据中已有研究报告、方法论、标准化资料、TikTok 业务笔记等 Markdown 文件。Library 是官网非常值得放大的“组织资产沉淀”证据：每次 Agent 执行不只是一次回答，还能留下可复用、可审阅、可归档的工作成果。

### 2.7 管理、身份和数据隔离

代码已确认存在：

- username/password 登录
- session auth
- admin 与普通用户角色
- 管理员创建用户
- 用户启用/停用
- 用户删除
- Agent、Chat、Autopilot、Run、Share 的 user ownership
- Marketplace Agent 的发布和安装

当前 Settings 中可见 General 和 Users 两个 tab。README/设计规格也明确记录了 user-owned data isolation。

这部分是企业版官网的可信度基础，但目前仍需要补充完整的企业安全说明、权限模型、审计日志范围、备份策略、部署拓扑和合规边界，不能仅用“安全”“私有”几个词带过。

### 2.8 Marketplace Agent 发布与安装

代码和设计规格已确认：

- 用户自己的 Agent 是 working copy。
- 发布到 Marketplace 时保存为不可变快照。
- 其他用户安装时复制成自己的 Agent。
- 发布内容包含 Agent 行为配置，不包含所有者、聊天数量等运行元数据。

这是“企业经验可复制”的重要基础，未来可以转译为：把专家经验、部门 SOP 和项目方法封装成组织自己的 Agent 模板，并在团队内复用。

### 2.9 技术架构与部署基础

项目 README 和部署文档确认：

- FastAPI 提供 API 和静态前端。
- Pi 通过 RPC/JSONL 承担 Agent 执行、工具调用、流式事件和会话历史。
- TinyDB 保存平台元数据，不复制 Pi 的消息正文。
- 生产部署使用 Docker Compose、独立 release 目录、共享数据目录和 NGINX HTTPS 反向代理。
- Provider、Model、Thinking level 从 Pi 的模型目录发现，可按 Agent 覆盖全局默认值。
- Skill、Extension、MCP 资源从工作区发现，并在 Agent 上显式选择。
- JSONL 日志、`X-Request-ID` 和持久化日志目录已存在。
- 文件服务同时检查文件是否由该 Chat 的 write/edit 工具产生，以及路径是否位于工作目录内。

需要注意：项目自身把当前状态定义为 MVP/active experiment；`PI_CWD` 不是安全沙箱，部署文档也明确没有把它描述成 sandbox。官网不能把当前实现宣传成已经完成的企业级安全隔离产品，应该将“现有能力”“交付方案”“需要按客户环境配置的安全边界”分开写。

## 3. 官网现状观察

### 3.1 当前官网已经做对的地方

本次打开的官网首页标题为 “Build your first AI agent without deploying anything”，副标题强调：browser-based、non-coders、real task、workflow、approved tools/data、inspect every result。

页面已经尝试表达以下方向：

- 从真实工作任务切入，而不是从基础设施切入。
- 强调 Agent team、数据访问、交付物和可检查执行。
- 用 Amazon seller research、WeChat/Lark content operations、research-to-report、internal operations copilot 等场景代替纯技术 demo。
- 提到 session history、tool traces、generated files、costs。
- 首页视觉使用大字号黑体、米灰背景、绿色强调色和工作流卡片，整体已经比“技术项目介绍页”更接近产品型官网。

### 3.2 关键错位

#### 定位错位

“without deploying anything”“browser-based”“for non-coders”把最强的产品入口讲成了轻量试用工具，却没有讲清楚企业最终购买的是：私有部署、方案交付、内部能力沉淀和持续运营。

#### 商业模式错位

Pricing 页面主打 Free / Starter / Pro 和 monthly credits，价格为 USD 0、9.9、99，并出现 subscribe、credit top-ups 等 SaaS 语言。这与“不是 SaaS、面向小 B 私有化部署”的商业模式直接冲突，应从官网主导航和首页主叙事中移除，或降级为公开试用/体验版说明。

#### 客户价值仍然不够具体

页面讲了“traceable”“governed access”“reusable methods”，但缺少客户能直接判断的结果：

- 哪些岗位可以先落地。
- 交付周期如何分阶段。
- 客户需要提供什么。
- 交付后企业得到哪些 Agent、Skill、MCP、知识库和流程资产。
- 如何迁移到客户自己的模型和基础设施。
- 哪些数据留在客户内网。
- FDE 在现场具体做什么。

#### 技术名词压过组织变化

MCP、Skills、credentials、connectors、orchestration 等词对技术读者有用，但对老板、业务负责人和 IT 负责人来说，需要先翻译成“经验资产、业务权限、系统连接、流程自动化、结果审计”。技术词应作为证据或展开层，而不是第一层价值语言。

#### 可信度证据不足

当前首页的 testimonials 使用了较泛化的人名、职位和描述；如果没有真实客户授权，建议改为匿名但可验证的项目结果，或者明确标注为示例。企业客户更关心部署方式、项目边界、数据控制、交付过程和可量化成果。

## 4. 建议的品牌定位

### 4.1 推荐定位句

中文：

> OhMyAgent，为企业部署真正能干活的 AI 工作系统。

英文：

> OhMyAgent builds private AI work systems around the way your business actually works.

### 4.2 推荐解释句

> 我们以 FDE + 私有化部署的方式，帮助企业把模型、内部知识、专家经验、业务工具和重复流程组合成可运行的 AI Agent 系统，并在企业自己的环境中持续迭代。

### 4.3 不建议继续作为主标题的说法

- Build your first AI agent without deploying anything
- Agent Platform for non-coders
- Credit-based agent runs
- 一个能调用很多工具的 Agent 平台

这些内容可以留在产品体验页或开发者文档，但不适合作为面向企业决策者的首页主叙事。

## 5. 官网应重点讲的客户价值

### 5.1 企业为什么现在需要它

- 企业已经有大量 SOP、专家经验和业务资料，但分散在文档、聊天记录和个人电脑里。
- 大模型能对话，却不天然理解企业流程、权限和交付标准。
- 直接采购通用 SaaS 会带来数据边界、模型绑定、流程不可控和资产无法沉淀的问题。
- 企业需要的不只是一个模型账号，而是一套能在自己环境里运行、审计和持续优化的 AI 工作系统。

### 5.2 OhMyAgent 做什么

把以下五层组装成一个可以交付的工作系统：

1. 模型层：按企业需求选择和切换模型，避免单一厂商绑定。
2. 方法层：把 SOP、专家经验、写作规范、研究方法固化为 Skills 和 Agent instructions。
3. 工具层：连接企业内部系统、外部数据源、MCP、Extensions 和业务 API。
4. 流程层：用 Chat、Autopilot、Agent Teams 和连接器让任务真正跑起来。
5. 治理层：权限、用户隔离、执行记录、文件资产、结果审阅和持续优化。

### 5.3 客户最终得到什么

- 一批围绕真实岗位交付的企业 Agent。
- 一套可复用的内部 Skills、SOP 和工作方法库。
- 一套连接业务系统的数据与工具层。
- 一套可追溯的运行和结果资产。
- 一套能由企业自己掌控模型、数据和部署边界的 AI 基础能力。
- 一支在项目现场帮助梳理流程、设计 Agent、接入系统并陪跑的 FDE 团队。

## 6. 推荐官网信息架构

建议官网主导航从“Platform / Pricing / Blogs / Docs / About”调整为：

- 首页：从企业工作问题和落地结果切入。
- 解决方案：按企业场景/岗位组织，不按技术模块组织。
- 产品系统：用一张清晰图解释 Agent、Skills、Tools、MCP、Models、Workflows、Governance 的关系。
- 私有化部署：部署模式、数据边界、模型选择、IT 配合、交付流程。
- FDE 服务：Discovery、Pilot、Build、Deploy、Operate 五阶段。
- 案例与方法：真实项目、结果、交付前后对比、可复用资产。
- 资源：文档、文章、Agent 方法论、行业洞察。
- 联系我们：明确“申请一次企业 AI 工作诊断”，不要只写 Contact。

Pricing 不应成为主导航重点。可以改为“部署与合作”或“Talk to us”，按场景、用户数量、部署复杂度、连接系统和 FDE 服务范围进行项目报价。

## 7. 推荐首页结构

### 第一屏

主标题聚焦企业结果：

> 把企业最重要的工作，变成真正能运行的 AI 系统。

副标题：

> OhMyAgent 通过 FDE 与私有化部署，把企业的知识、经验、工具和流程封装成可运行、可审计、可持续迭代的 AI Agent 工作系统。

主 CTA：`预约企业 AI 工作诊断`  
次 CTA：`查看 Studio 如何工作`

视觉上建议展示一条“业务任务 → Agent 协作 → 内部工具/知识 → 审阅结果 → 组织资产”的真实工作链路，避免单纯聊天框和技术节点堆叠。

### 第二屏：先讲痛点

标题示例：

> 企业缺的不是一个模型账号，而是一套能进入工作现场的 AI 方法。

用三到四个痛点卡片：

- 经验在个人手里，无法复制。
- 工具和数据分散，Agent 只会空谈。
- 通用 SaaS 无法进入敏感业务流程。
- 试验很多，真正上线很少。

### 第三屏：展示解决方案闭环

用可视化系统图展示：

`业务岗位 / 工作任务 → Agent → Skill / 企业知识 → Tools / MCP → Model → Workflow / Autopilot → 结果资产 / 审计`

重点解释每个模块对应的业务语言，不直接把 MCP、RPC、JSONL 放在首层。

### 第四屏：私有化与模型自主

这里必须成为核心卖点，而不是 FAQ 里的附属信息：

- 部署在客户自己的云、VPC 或内网环境。
- 企业数据和执行记录按客户边界管理。
- 可接入客户指定的模型和 Provider。
- 允许逐步替换模型，不把业务方法绑死在某一个模型厂商上。
- 根据 IT 和合规要求设计权限、日志、备份和网络访问策略。

所有安全、合规、隔离表述需要以实际可交付范围和客户部署方案为准，避免绝对化承诺。

### 第五屏：FDE 交付方法

建议用五阶段时间线：

1. Discover：梳理高价值、可验证的业务工作。
2. Design：设计岗位 Agent、Skills、工具和结果标准。
3. Build：接入内部资料、MCP、系统和模型。
4. Deploy：部署到客户环境，配置账号、权限和运行策略。
5. Operate：陪跑、评估、迭代，把一次项目变成内部能力。

### 第六屏：优先场景

首批建议只选三到四个垂直案例，且每个案例必须写清“输入、过程、输出、组织收益”：

- 跨境电商研究与内容运营。
- 企业研究、竞品与行业情报。
- SOP/合规检查和知识问答。
- 内容生产、报告生成和周期性运营。

### 最后 CTA

> 带一个真实业务流程来，我们一起判断它是否值得被 Agent 化。

CTA：`预约工作流诊断`、`申请私有化方案`。

## 8. 设计方向

### 8.1 视觉气质

建议从“AI 工具 SaaS”转向“AI 科技公司 + 交付型系统”：

- 更强的编辑型排版和留白。
- 深色墨黑、暖白、低饱和绿色/电光蓝作为克制的识别色。
- 用真实工作流、文件、权限、系统连接和人员协作做视觉主体。
- 少用漂浮的渐变球、机器人头像、过度霓虹和纯技术网络图。
- 页面要同时让 CEO、业务负责人和 IT 负责人看懂。

### 8.2 文案原则

- 先讲客户要完成的工作，再讲 Agent 如何完成。
- 先讲私有化和可控性，再讲模型/工具生态。
- 把“Skill”解释成企业方法资产，把“MCP”解释成系统和数据连接层。
- 把“Trace”解释成可复盘的执行记录，把“Library”解释成组织成果资产。
- 少用“灵活、强大、高效、智能”等空泛词，改为可观察的交付结果。

## 9. 后续官网建设前必须补齐的事实

以下内容目前不能仅凭本次代码和页面观察确认，正式官网上线前需要产品方提供：

- 支持的私有化部署形态：单机、Docker、Kubernetes、VPC、内网、离线等。
- 数据是否始终留在客户环境，哪些外部请求可选，哪些必须出网。
- 当前实际支持的模型 Provider、模型清单和切换机制。
- 企业级权限的粒度：用户、团队、Agent、Skill、MCP、文件、会话、日志。
- 审计日志保存范围、保存时长、导出能力和管理员可见范围。
- 备份、恢复、升级、回滚和灾备方案。
- FDE 服务的标准交付周期、角色分工、客户输入和验收标准。
- 可公开的真实客户、行业、案例和量化结果。
- Agent Teams 的实际可用程度；当前 Studio Marketplace 页面显示该类资源为空。
- 当前生产环境的安全边界，尤其是 Pi 工作目录、Extension 执行权限和 MCP 凭据管理。
- 商业报价模型：按项目、部署规模、Agent 数量、服务周期、连接系统还是用户数计费。

## 10. 结论

官网改造的核心不是把当前页面“做得更漂亮”，也不是把技术模块换成更时髦的视觉。真正要改的是购买理由：

> 从“在线创建和使用 AI Agent”升级为“帮助企业把知识、经验、工具和流程变成自己的 AI 工作系统”。

Studio 已经提供了很好的产品证据：Agent 配置、模型选择、工具和资源组合、Marketplace、定时运行、结果文件、历史会话、用户隔离和 Agent 发布安装。官网下一步应该围绕这些真实能力，建立“企业问题 → FDE 方法 → 私有化系统 → 可复用组织资产”的叙事闭环。

后续单独建立官网项目时，建议先完成这份资料中的事实补齐，再进入首页线框、品牌方向和文案方案；不要先从技术栈或组件库开始。

## 附录：本次取证文件

本次浏览过程保存了以下临时截图，作为审查取证参考：

- `work/site-home.png`
- `work/studio-agents.png`
- `work/studio-autopilots.png`
- `work/studio-marketplace.png`
- `work/studio-library.png`

截图是本次观察的辅助证据，不代表正式官网设计稿，也不应直接作为公开宣传素材。
