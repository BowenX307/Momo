# uni · Unity 场景端接入说明书

> 版本 2026-07-14 · 后端已上线,可直接联调
> 本说明书配套文件:`UniClient.cs`(接入用的客户端脚本)

---

## 目录

1. [这是什么](#一这是什么)
2. [五分钟接入](#二五分钟接入)
3. [工作原理:一次对话怎么跑的](#三工作原理一次对话怎么跑的)
4. [接口详解:请求与响应字段](#四接口详解请求与响应字段)
5. [三个状态:待机 / 思考 / 说话](#五三个状态待机--思考--说话)
6. [小人反应动画:后端直接告诉你演哪个](#六小人反应动画后端直接告诉你演哪个)
7. [播放语音:base64 → AudioClip](#七播放语音base64--audioclip)
8. [人格](#八人格)
9. [接口自测](#九接口自测)
10. [注意事项](#十注意事项)
11. [联系方式](#十一联系方式)

---

## 一、这是什么

uni 是一个情绪陪伴 AI。用户对小人说话,后端会:**理解这句话 → 生成回答 → 合成语音 → 判断用户情绪 → 决定小人该做什么反应**,然后把结果一次性交给你,由 Unity 里的小人"说"出来、"演"出来。

**你只需要对接一个接口。** 一次请求,同时拿到「回答文字」「回答语音」「用户情绪」「小人反应动画」。

配套的 `UniClient.cs` 已经把调接口、拆数据、播语音、切状态全部封装好,你基本不用碰网络代码。

| 交付物 | 说明 |
|---|---|
| `uni 接入说明书.md` | 本文件 |
| `UniClient.cs` | Unity 客户端脚本,拖进 `Assets/` 即用 |

**服务端地址:`https://uniai.net.cn`**(已部署,脚本内已默认配置)。
Unity 端**无需任何密钥、无需安装任何依赖**。

---

## 二、五分钟接入

1. 把 `UniClient.cs` 拖进 Unity 工程的 `Assets/` 目录。
2. 场景里新建一个空物体,挂上 `UniClient` 组件。
3. 把小人的 `AudioSource` 拖进组件的 **Audio Source** 槽位。
4. 在你自己的脚本里订阅事件,并在用户说完话时调用 `Say()`:

```csharp
// 初始化时订阅一次
uniClient.OnStateChanged += s => animator.SetInteger("state", (int)s); // 0待机 1思考 2说话
uniClient.OnReaction     += r => PlayReaction(r);                      // 小人反应动画
uniClient.OnEmotion      += e => { /* 用户情绪,想用就用 */ };
uniClient.OnReply        += t => subtitle.text = t;                    // 字幕

// 用户说完一句话时调用,剩下的它全包了
uniClient.Say("今天好累啊");
```

调用 `Say()` 后,小人会自动:**进入思考 → 播反应动画 + 说出回答 → 回到待机**。上下文由脚本内部维护,你不用管。

你要写的只有两件事,而且都是你的本行:
- **动画怎么演** —— 收到 `OnStateChanged` / `OnReaction` 播对应片段;
- **字幕怎么显示** —— 收到 `OnReply` 显示文字。

---

## 三、工作原理:一次对话怎么跑的

一轮对话的数据流:

```
① 用户说完话(语音转文字,或直接打字)
        │  文字
        ▼
② UniClient 把这句话发给后端  ← 唯一和服务器打交道的一步
        │
        ▼
③ 后端一次性算好,打包返回:
        · 回答文字   "累就先别硬撑了"
        · 回答语音   (MP3)
        · 用户情绪   "疲惫"     ← 用户什么心情
        · 小人反应   "关心"     ← 小人该演什么动画
        │
        ▼
④ UniClient 拿到包裹:播反应动画 + 播语音 + 抛字幕
        │
        ▼
⑤ 语音播完,小人回到待机,等下一句
```

要记住的一个区分:**「用户情绪」和「小人反应」不是一回事。**
用户"疲惫"(情绪),小人演的是"关心"(反应)。后端已经帮你把这层转换做好了,直接用 `reaction` 即可(详见第六节)。

---

## 四、接口详解:请求与响应字段

> 正常情况下 `UniClient.cs` 已经封装好,以下仅供你需要自定义时查阅。

| | |
|---|---|
| 线上 | `POST https://uniai.net.cn/v1/chat/demo` |
| 本地联调 | `POST http://127.0.0.1:8000/v1/chat/demo` |
| Content-Type | `application/json` |
| 耗时 | 约 2~4 秒(含语音合成) |

### 请求体

```json
{
  "user_text": "今天好累啊，什么都不想做",
  "persona": "iris",
  "scene": "",
  "history": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_text` | string | ✅ | 用户这一句话 |
| `persona` | `"momo"` \| `"iris"` \| `"rocky"` | 否 | 人格,默认 `momo`。切人格时清空 `history` |
| `scene` | string | 否 | **第一句留空**(`""` 即可),后端自动判断场景;之后把响应里的 `scene` 原样带回来,可省一次模型调用,**后续每轮快约 1 秒** |
| `history` | array | 否 | 最近对话历史,最多 20 条(10 轮),**不含本轮 `user_text`** |

`history` 元素格式:

```json
[
  { "role": "user",      "content": "今天好累" },
  { "role": "assistant", "content": "累的话就先歇会儿…" }
]
```

### 响应体

```json
{
  "reply": "累就先别硬撑了，喝口水，坐一会儿。",
  "emotion": "疲惫",
  "reaction": "关心",
  "audio_base64": "SUQzBAAAAAA...(MP3 的 base64)",
  "audio_content_type": "audio/mpeg",
  "scene": "late_night",
  "safety_flag": "ok",
  "degraded": false,
  "is_mock": false,
  "request_id": "..."
}
```

| 字段 | 用来干嘛 |
|---|---|
| `reply` | 小人说的话,显示成字幕 |
| `emotion` | **用户**的情绪(12 个标签之一,见下),想用可用;不用也行 |
| `reaction` | **小人该播的反应动画**(核心,见第六节)。空串表示无,播 Idle |
| `audio_base64` | 小人的语音,MP3 的 base64。**播放时长 = 说话状态时长** |
| `scene` | 下一轮请求原样带回 |
| `safety_flag` | `"ok"` 以外表示触发了安全兜底(如 `crisis_keyword`),可加提示 |
| `degraded` | `true` = 真模型挂了、当前是兜底回复,可显示"临时离线" |
| `is_mock` | `true` = 没配 key,跑的是假数据 |

### emotion 取值(固定 12 个之一)

```
焦虑  委屈  孤独  愤怒  失落  疲惫  迷茫  难过  开心  平静  压抑  无奈
```

空串表示未识别。**注意:这是"用户"的情绪,不能直接拿来当小人动画** —— 小人该演什么请用 `reaction`。

---

## 五、三个状态:待机 / 思考 / 说话

这三个状态**不需要问服务器**,`UniClient` 已经按请求的生命周期帮你切好,你只要响应 `OnStateChanged`:

| 状态(枚举值) | 什么时候 | 小人 |
|---|---|---|
| `Idle` = 0 | 没有请求进行中 | 待机(可用 Idle / Walking) |
| `Thinking` = 1 | 请求已发出,回答还没回来 | 思考(歪头 / 转圈) |
| `Speaking` = 2 | 回答已回来,正在播语音 | 说话(播 `reaction` 反应动画 + 口型) |

播完自动回 `Idle`。

**为什么不做成一个"状态接口":** 这三个状态就是"这次请求进行到哪一步了",而请求是 Unity 发起的,本地就精确知道。若改成向服务器查询,每次都要多一次网络往返(约 100~300ms),会导致**小人张嘴比声音慢半拍**,呈现为口型对不上。本地推导零延迟、且不会状态错乱。

---

## 六、小人反应动画:后端直接告诉你演哪个

这是这套接口的重点。

小人在"说话"时该做什么表情/动作,**后端已经据它这句回答的语气判断好了**,放在响应的 `reaction` 字段里。你直接拿去播对应动画即可,**不用自己从情绪去映射,一步到位**。

### 取值(共 6 个反应动画)

| reaction | 含义 | 小人 |
|---|---|---|
| `开心` | 回答轻松、逗趣、分享愉快 | 高兴 |
| `伤心` | 回答在陪着一起难过、共情 | 难过 |
| `疑惑` | 回答在困惑、一起想、反问 | 歪头疑惑 |
| `肯定` | 回答在顺着用户、认同 ta | 点头认同 |
| `否定` | 回答在反驳、纠正用户的消极自我判断("你没那么糟") | 摇头、"不是这样" |
| `关心` | 回答在关切、安慰、叮嘱照顾好自己 | 关切、靠近 |

空串 `""` 表示没有反应(见下面的人格差异),此时播 `Idle`。

### ⚠️ 每个人格能用的反应不一样

后端**只会返回该人格真有动画的反应**,所以你不会收到一个没做过的动画:

| 人格 | 后端可能返回的 reaction |
|---|---|
| **iris**(直率爽朗) | 开心 / 伤心 / 疑惑 / 肯定 / 否定 —— 无"关心" |
| **rocky**(温柔知性) | 开心 / 伤心 / 疑惑 / 关心 —— 无"肯定 / 否定" |
| **momo** | 暂无动画,`reaction` 恒为空串 → 播 Idle |

> 如果之后补了动画(比如 iris 加"关心"、momo 出整套),告诉后端,后端放开对应人格的取值即可,Unity 端代码不用改。

### 接入示例

```csharp
uniClient.OnReaction += reaction =>
{
    // reaction 为 "开心"/"伤心"/"疑惑"/"肯定"/"否定"/"关心" 或 ""
    string clip = string.IsNullOrEmpty(reaction) ? "Idle" : reaction;
    _pendingReactionClip = clip;   // 存起来,等进入 Speaking 状态时播
};

uniClient.OnStateChanged += s =>
{
    switch (s)
    {
        case UniState.Idle:     animator.Play("Idle");                break;
        case UniState.Thinking: animator.Play("Idle");                break; // 或思考动画
        case UniState.Speaking: animator.Play(_pendingReactionClip);  break; // 播反应动画
    }
};
```

要点:`OnReaction` 先到(把要演的动画存下),随后状态变成 `Speaking` 时再播,这样反应动画和语音同时开始。

---

## 七、播放语音:base64 → AudioClip

> `UniClient.cs` 已内置此逻辑,以下说明其原理,便于你排查。

Unity 不能直接从内存解 MP3,需**先落临时文件再加载**:

```csharp
var path = Path.Combine(Application.temporaryCachePath, "uni_reply.mp3");
File.WriteAllBytes(path, Convert.FromBase64String(base64));

using var req = UnityWebRequestMultimedia.GetAudioClip("file://" + path, AudioType.MPEG);
yield return req.SendWebRequest();
audioSource.clip = DownloadHandlerAudioClip.GetContent(req);
audioSource.Play();
```

**口型同步**:调用 `uniClient.CurrentMouthOpen()`,返回 0~1 的实时音量,可直接驱动嘴部开合幅度。无需额外接口。

---

## 八、人格

在 `UniClient` 组件的 Inspector 面板改 `persona` 字段。三个人格的**措辞风格与语音音色都不同**:

| 取值 | 人格 |
|---|---|
| `momo` | 温柔水母,稳定陪伴(默认;暂无反应动画) |
| `iris` | 高洞察、略毒舌的少年,少年男声 |
| `rocky` | 白斗篷小精灵,知性直接 |

切换人格时脚本会自动清空对话上下文。

---

## 九、接口自测

接入前想独立验证服务端,执行:

```bash
curl -X POST https://uniai.net.cn/v1/chat/demo \
  -H "Content-Type: application/json" \
  -d '{"user_text":"我觉得我什么都做不好","persona":"iris"}'
```

正常会返回一段 JSON,含 `reply`(文本)、`emotion`(用户情绪)、`reaction`(小人反应)、`audio_base64`(语音)。`audio_base64` 很长属正常。

服务是否在线:浏览器打开 `https://uniai.net.cn/health`,看到 `"status": "healthy"` 即正常。

---

## 十、注意事项

- **响应耗时约 2~4 秒**(含语音合成)。这期间小人处于 `Thinking`,请确保思考动画能自然循环。
- **请求进行中重复调用 `Say()` 会被忽略**,以避免语音叠音。需要"打断"能力请找后端沟通。
- **反应动画的 `肯定` 与 `否定`** 在"半反驳半认同"的句子上偶尔会互串。两者都是善意反应,视觉上不突兀;如发现明显不对,把例子发给后端调。
- **若最终要导出 WebGL 版**,浏览器会有跨域限制。当前服务端已允许跨域,不影响联调;正式发布前需把目标域名加入白名单,届时提前告知后端。
- 另有流式接口可"逐句发声"(首句 1~2 秒即可开口,体感更快),但需在 Unity 端自行实现 SSE 解析。**建议先用当前方案跑通,动画调顺后再评估升级。**

---

## 十一、联系方式

接口行为、字段含义、放开某人格的反应取值、新增返回值等,请联系后端负责人 Bowen。
不必自己猜;尤其**不要为了拿状态或反应去写轮询**——它们都已经在返回里给你了。
