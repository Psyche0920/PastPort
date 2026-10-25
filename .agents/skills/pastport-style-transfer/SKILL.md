---
name: pastport-style-transfer
description: 将已标注的 PastPort 博物馆环境自动装配为完整动画360全景，保留对象、证据、热点、导航与人工编辑；支持复用现成图或受额度约束的 Codex SDK 转绘。
---

# 动画全景自动化

输入是已标注的 PastPort schema 4 环境目录，不是照片到史料匹配任务。读取[自动化接口与处理方法](../../../docs/VR_ANIMATION.md)，通过仓库的 `AnimationWorkflow` 或 `AnimationNode` 执行；不依赖此前聊天中的路径、编号或口头步骤。

- 全景原图决定全部几何与实体；仓库 `src/pastport_pdf_vr/animation_assets/approved-style.png` 是用户已选的动画质感参考，不能移植其中的物件。固定政策在同目录 `policy-v1.txt`。电脑、椅子、现代厂房、窗户和消防设备仍是原实体，不根据历史关联改成历史物件。
- 图像风格明确完全动画化，采用干净色块、柔和立体体积与有设计的材质笔触；暖金光为主，少量原有紫红灯光作为现场特征。光照不以泛黄滤镜或摄影细纹代替动画。补绘仅是美术推断，不是史实证据。
- 用户提供两个点位现成图时，使用 `ExistingPanorama` 与源全景哈希绑定，覆盖全部点位，走 `existing_panoramas` 模式。该模式没有 SDK 查询、模型调用或额度台账，保留图片原始字节，不把它称为重新生成验证。
- 新生成只在有明确授权与有限 `SubscriptionGrant` 时执行。使用现有 Codex 订阅登录、原模型与用量台账；不得另接付费 API、复制凭据、切换模型、自动重试或通过新建工作区绕过未知用量。一个视点规划六个方向，不自行批量抽卡。
- 每个方向使用同一风格图；第一视点后续面参考已画好的正面，其他视点参考第一视点相同方向，参考只负责材质与光照，不负责几何。四周、顶面、地面全部覆盖，带5%保护边，按 `right,left,up,down,front,back` 重投影。工具原生输出不足时停止，不放大冒充高清。
- 保留源目录与数据库；输出是新目录。对象身份、历史绑定、引文、来源、人工介绍、人工坐标及导航继承原数据；新纹理采用新哈希和修订，继承角度作为待人工验收的提案。未有效绑定的项不补造热点。
- 交付动画环境目录、ZIP、`animation-manifest.json` 及 Story Agent 交接说明；流程执行成功不等于画质、接缝、对象位置或设备验收。用户明确由其手工验收，本轮不启动额外模型、自动测试、浏览器审核或服务。

既有 Studio 的匹配 PDF 上传入口保持原作用；新动画流程是可单独调用的 Python/LangGraph 节点，尚未新增 Studio 动画上传页面。不能把它描述成已经接入所有供应商网站或已经部署的公共网站。

## Additional 3D path

The existing animation branch is now `codex/environment-stylization`; the matching
branch is `codex/matched-environment`. Read `docs/STYLIZATION3D.md` for the exact
whole-tour package and typed graph contracts. Consume one complete tour archive;
return one complete archive with independent worlds and their navigation. Reuse
source-bound painted maps through the existing animation stage; apply them to
real SPZ appearance, not only 2D screenshots. Preserve one tour-level review
authority and per-view spatial state. Automatic camera estimates proceed without
waiting for human intervention, but are never recorded as human-confirmed.
Current baking supports SPZ v2/SH0 and preserves geometry. It cannot claim to fix
wrong structures, missing geometry or all far-view inconsistencies. Mark those
limitations and retain the current Muradiye demo as the minimum acceptance baseline.
User manually accepts output; do not add model calls, repeated browser tests or
service restarts without task authorization. Complete-tour extraction and packaging
are not image generation. Keep source rights, evidence, identities and manual edits.
