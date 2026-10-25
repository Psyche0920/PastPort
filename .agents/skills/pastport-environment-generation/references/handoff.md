# Agent生成的交接记录

这些文件由Agent处理输入后写出，不要求用户手填。证据、图像与坐标必须来自已登记的新输入。它们不是与主应用约定的新共享SDK。

`evidence/` 包含 `input.pdf`（输入匹配PDF原样副本）、`source.pdf`（已登记的原文来源；无补充原件时使用输入PDF自身并标明来源层级）、`objects.json`、`inputs.json`、`quote-regions.json` 和 `media/`。不把输入匹配PDF的页号冒称原始史料页号。

`objects.json` 是 `{ "title": "本轮项目标题", "objects": [...] }`。每项字段与 `Entity.parse` 一致：

- `number` 正整数显示编号，`object_id` 稳定现代实体ID，`name`、`boundary`。
- `history_id` 稳定历史主体ID，`history` 名称，`parent` 范围；实体身份不得仅靠名称或数据库唯一性判断。
- `page` 为source.pdf中引文的1起始页号；`image_page`、`image_box` 为已核实图像页与归一化选区。没有实物图时 `image_page=null`，使用真实原文截图。
- `explanation` 中文说明，`proxy` 替代设定，`limit` 限制，`quote` 未改写的英文引文。
- `observations`：每条有 `photo_number`、`observation_status`、`region_normalized`（左上/右下四坐标，0–1）和 `basis`。仅真实可见项标 `visible`；其余坐标为null。

`inputs.json`：`input_page_count` 来自已准备PDF；`photos` 每条有 `number`、`path`（登记的照片或从输入PDF提取的可复核照片文件）、`sha256`、`oriented_size`。从PDF抽取的图片需保留源页和页面选区依据，不能假称用户原照片文件。照片保存为 `media/photo-NN.jpg`；历史选区或真实文字截图保存为 `media/history-NN.png`（NN为对应物件编号）。

`quote-regions.json` 是数组，每项包含 `number`、`page`、`normalized_text`、`start`、`end`；`normalized_text[start:end]` 必须等于该项 `quote`。上下文应来自source.pdf的真实抽取记录，不得由模型补写。使用 `native_column_text` 可保留原文栏的抽取版本；纸面图页和引文页可以不同。

`locations.json` 包含 `input_html_sha256`（本轮VR原文件字节哈希）、`locations` 数组与 `relationship_reviews` 数组。每个位置：`object_number`、`source_scene_id`、`panorama_sha256`（解码图片字节哈希）、`pixel_center`（本轮完整原图像素，不是缩小图/透视图像素）、`basis`。一个物件在每视点至多一个代表热点；源视点ID必须来自本轮tour.json。

每条关系记录：`whole_object_number`、`part_object_number`、`historical_relation`（`fixed_part_of`/`contained_in`）、`modern_relation`（`within_whole`/`attached_to_whole`/`unrelated`/`not_confirmed`）、`verdict`（`verified`/`rejected`/`pending`）和非空 `reason`（可追溯的判断依据）。识别到整体和部件同时被映射时必须记录；未核实或被否定的部件被排除。程序会拒绝把无关物件声明为关系已核实，但不能自行证明未登记的关系不存在。

装配器拒绝输入PDF/坐标文件哈希不符、重复身份、重复视点位置及越界坐标。它不代替Agent对图像、身份、来源语义和关系完整性的判断。完成后先按Skill自检，再交用户实际候选；不能声称仅有JSON就完成了识别。
