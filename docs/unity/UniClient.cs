// uni · Unity 接入客户端
// ------------------------------------------------------------------
// 用法:
//   1. 把这个文件拖进 Unity 的 Assets/ 里
//   2. 场景里建个空物体,挂上 UniClient,把小人的 AudioSource 拖到 Audio Source 槽里
//   3. 在你自己的脚本里:
//
//        uniClient.OnStateChanged += s  => animator.SetInteger("state", (int)s);  // 待机/思考/说话
//        uniClient.OnEmotion      += e  => SetFace(e);                            // 用户的情绪
//        uniClient.OnReply        += t  => subtitle.text = t;                     // 字幕
//
//        uniClient.Say("今天好累啊");   // 用户说了一句话 → 小人开始思考 → 说话 → 回到待机
//
// 三个状态不用问服务器,这个脚本已经按请求的生命周期帮你切好了。
// 详细字段说明见 docs/unity-api.md。有问题找后端(Bowen)。
// ------------------------------------------------------------------

using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public enum UniState
{
    Idle = 0,      // 待机:没人在说话
    Thinking = 1,  // 思考中:请求已发出,还没拿到回答
    Speaking = 2,  // 说话中:正在播放语音
}

public class UniClient : MonoBehaviour
{
    [Header("服务器")]
    [Tooltip("线上 https://uniai.net.cn  /  本地联调 http://127.0.0.1:8000")]
    public string baseUrl = "https://uniai.net.cn";

    [Header("人格")]
    [Tooltip("momo(温柔水母) / iris(毒舌损友,少年音) / rocky(知性小精灵)。切换时会自动清空上下文。")]
    public string persona = "momo";

    [Header("小人的嘴")]
    public AudioSource audioSource;

    // ── 事件:Unity 那边订阅这三个就够了 ─────────────────────────
    /// <summary>待机 / 思考中 / 说话中。切换的那一刻触发。</summary>
    public event Action<UniState> OnStateChanged;
    /// <summary>**用户**的情绪(不是小人的)。12 个中文标签之一,见文档;可能是空串。</summary>
    public event Action<string> OnEmotion;
    /// <summary>小人这一轮该播的反应动画:开心/伤心/疑惑/肯定/否定/关心 之一。
    /// 空串表示无(momo 或判定失败),此时播 Idle。取值随人格,见文档。
    /// 在小人"说话"期间播这个动画最自然。</summary>
    public event Action<string> OnReaction;
    /// <summary>小人这一轮说的话,用来显示字幕。</summary>
    public event Action<string> OnReply;
    /// <summary>出错了(断网 / 服务器挂了)。状态会自动回到 Idle。</summary>
    public event Action<string> OnError;

    public UniState State { get; private set; } = UniState.Idle;

    // 会话上下文
    string _scene;                                     // 第一轮为空,之后用后端返回的,能省一次模型调用
    readonly List<Msg> _history = new List<Msg>();     // 最多留 20 条(10 轮)
    const int MaxHistory = 20;

    string _persona;                                   // 记住上次用的人格,变了就重置会话

    /// <summary>用户说了一句话。整个 思考→说话→待机 的流程由这里驱动。</summary>
    public void Say(string userText)
    {
        if (string.IsNullOrWhiteSpace(userText)) return;
        if (State != UniState.Idle) return;            // 上一轮还没结束,忽略(防止叠话)
        StartCoroutine(SayRoutine(userText));
    }

    /// <summary>清空对话上下文,重新开始一段对话。</summary>
    public void ResetConversation()
    {
        _history.Clear();
        _scene = null;
    }

    IEnumerator SayRoutine(string userText)
    {
        if (_persona != persona) { ResetConversation(); _persona = persona; }  // 换人格 = 换个人,上下文不该带过去

        // ── Thinking ──────────────────────────────────────────
        SetState(UniState.Thinking);

        var payload = JsonUtility.ToJson(new ChatRequest
        {
            user_text = userText,
            persona   = persona,
            scene     = _scene,                        // null 会被序列化成 "",后端认
            history   = _history.ToArray(),
        });

        ChatResponse res = null;
        using (var req = new UnityWebRequest(baseUrl + "/v1/chat/demo", "POST"))
        {
            req.uploadHandler   = new UploadHandlerRaw(Encoding.UTF8.GetBytes(payload));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.timeout = 30;

            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
            {
                OnError?.Invoke(req.error);
                SetState(UniState.Idle);               // 失败也要回待机,别把小人卡在思考动画里
                yield break;
            }

            try { res = JsonUtility.FromJson<ChatResponse>(req.downloadHandler.text); }
            catch (Exception e) { OnError?.Invoke("解析响应失败: " + e.Message); }
        }

        if (res == null || string.IsNullOrEmpty(res.reply))
        {
            OnError?.Invoke("服务器返回了空回答");
            SetState(UniState.Idle);
            yield break;
        }

        // 记住上下文
        _scene = res.scene;
        _history.Add(new Msg { role = "user",      content = userText });
        _history.Add(new Msg { role = "assistant", content = res.reply });
        while (_history.Count > MaxHistory) _history.RemoveAt(0);

        OnEmotion?.Invoke(res.emotion);                // 用户情绪(想用就用)
        OnReaction?.Invoke(res.reaction);              // 小人该演的动画,准备好
        OnReply?.Invoke(res.reply);                    // 字幕

        // ── Speaking(播 res.reaction 这个动画 + 语音)──────────
        yield return StartCoroutine(PlayMp3(res.audio_base64));

        // ── 回到 Idle ─────────────────────────────────────────
        SetState(UniState.Idle);
    }

    /// <summary>base64 的 MP3 → AudioClip → 播。Unity 不能直接从内存解 MP3,先落临时文件。</summary>
    IEnumerator PlayMp3(string base64)
    {
        if (string.IsNullOrEmpty(base64)) yield break; // 没音频就跳过,别卡住

        string path = Path.Combine(Application.temporaryCachePath, "uni_reply.mp3");
        try { File.WriteAllBytes(path, Convert.FromBase64String(base64)); }
        catch (Exception e) { OnError?.Invoke("音频写入失败: " + e.Message); yield break; }

        using (var req = UnityWebRequestMultimedia.GetAudioClip("file://" + path, AudioType.MPEG))
        {
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success)
            {
                OnError?.Invoke("音频解码失败: " + req.error);
                yield break;
            }

            SetState(UniState.Speaking);
            audioSource.clip = DownloadHandlerAudioClip.GetContent(req);
            audioSource.Play();
            yield return new WaitWhile(() => audioSource != null && audioSource.isPlaying);
        }
    }

    /// <summary>说话时的实时音量 0~1,可以直接驱动嘴巴张开的幅度(口型同步不需要额外接口)。</summary>
    public float CurrentMouthOpen()
    {
        if (State != UniState.Speaking || audioSource == null || !audioSource.isPlaying) return 0f;

        var samples = new float[128];
        audioSource.GetOutputData(samples, 0);
        float sum = 0f;
        for (int i = 0; i < samples.Length; i++) sum += samples[i] * samples[i];
        return Mathf.Clamp01(Mathf.Sqrt(sum / samples.Length) * 6f);   // 6f 是经验系数,自己调
    }

    void SetState(UniState s)
    {
        if (State == s) return;
        State = s;
        OnStateChanged?.Invoke(s);
    }

    // ── 和后端 JSON 一一对应的数据类(JsonUtility 只认公开字段,名字必须完全一致)──
    [Serializable]
    public class Msg
    {
        public string role;      // "user" | "assistant"
        public string content;
    }

    [Serializable]
    public class ChatRequest
    {
        public string user_text;
        public string persona;   // momo | iris | rocky
        public string scene;     // 第一轮留空
        public Msg[]  history;
    }

    [Serializable]
    public class ChatResponse
    {
        public string reply;         // 小人说的话
        public string emotion;       // 用户的情绪:焦虑/委屈/孤独/愤怒/失落/疲惫/迷茫/难过/开心/平静/压抑/无奈
        public string reaction;      // 小人该演的动画:开心/伤心/疑惑/肯定/否定/关心;空串=播 Idle
        public string audio_base64;  // MP3
        public string audio_content_type;
        public string scene;         // 下一轮原样带回
        public string safety_flag;   // "ok" 以外表示触发安全兜底
        public bool   degraded;      // true = 模型挂了,当前是兜底回复
        public bool   is_mock;       // true = 假数据
        public string request_id;
    }
}
