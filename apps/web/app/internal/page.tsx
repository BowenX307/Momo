"use client";

/**
 * /internal —— 团队内部工作台(nginx 层已挡共享账号密码,访问权限不在这里管)。
 *
 * 目的:产品/设计/商业不用再靠口头/语音描述模糊的需求和 bug——这里一眼看到
 * IT 现阶段的 todolist,也能直接打字或录音提交新需求。
 */

import { useCallback, useEffect, useState } from "react";

import { VoiceInputButton } from "@/app/demo/_components/VoiceInputButton";
import {
  createFeedback,
  createTodo,
  deleteTodo,
  fetchFeedback,
  fetchTodos,
  updateFeedbackStatus,
  updateTodo,
  type FeedbackItem,
  type FeedbackKind,
  type FeedbackStatus,
  type TodoItem,
  type TodoStatus,
} from "@/lib/api/workboard";

const TODO_STATUS_LABEL: Record<TodoStatus, string> = {
  open: "待办",
  in_progress: "进行中",
  done: "已完成",
};

const FEEDBACK_STATUS_LABEL: Record<FeedbackStatus, string> = {
  new: "待处理",
  triaged: "已确认",
  done: "已完成",
};

const FEEDBACK_KIND_LABEL: Record<FeedbackKind, string> = {
  bug: "Bug",
  feature: "需求",
  other: "其他",
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function InternalWorkboardPage() {
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [newTodoTitle, setNewTodoTitle] = useState("");
  const [newTodoDetail, setNewTodoDetail] = useState("");
  const [addingTodo, setAddingTodo] = useState(false);

  const [authorName, setAuthorName] = useState("");
  const [feedbackKind, setFeedbackKind] = useState<FeedbackKind>("feature");
  const [feedbackContent, setFeedbackContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitOk, setSubmitOk] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [t, f] = await Promise.all([fetchTodos(), fetchFeedback()]);
      setTodos(t);
      setFeedback(f);
    } catch {
      setLoadError("加载失败,请确认后端服务正常");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAddTodo = useCallback(async () => {
    const title = newTodoTitle.trim();
    if (!title || addingTodo) return;
    setAddingTodo(true);
    try {
      const todo = await createTodo({ title, detail: newTodoDetail.trim() });
      setTodos((prev) => [...prev, todo]);
      setNewTodoTitle("");
      setNewTodoDetail("");
    } catch {
      setLoadError("添加待办失败");
    } finally {
      setAddingTodo(false);
    }
  }, [newTodoTitle, newTodoDetail, addingTodo]);

  const handleCycleStatus = useCallback(async (todo: TodoItem) => {
    const next: Record<TodoStatus, TodoStatus> = {
      open: "in_progress",
      in_progress: "done",
      done: "open",
    };
    const updated = await updateTodo(todo.id, { status: next[todo.status] });
    setTodos((prev) => prev.map((t) => (t.id === todo.id ? updated : t)));
  }, []);

  const handleDeleteTodo = useCallback(async (id: string) => {
    if (!confirm("确定删除这条待办?")) return;
    await deleteTodo(id);
    setTodos((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleSubmitFeedback = useCallback(async () => {
    const content = feedbackContent.trim();
    if (!content || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitOk(false);
    try {
      const item = await createFeedback({
        content,
        author_name: authorName.trim(),
        kind: feedbackKind,
      });
      setFeedback((prev) => [item, ...prev]);
      setFeedbackContent("");
      setSubmitOk(true);
      setTimeout(() => setSubmitOk(false), 2500);
    } catch {
      setSubmitError("提交失败,请重试");
    } finally {
      setSubmitting(false);
    }
  }, [feedbackContent, authorName, feedbackKind, submitting]);

  const handleCycleFeedbackStatus = useCallback(async (item: FeedbackItem) => {
    const next: Record<FeedbackStatus, FeedbackStatus> = {
      new: "triaged",
      triaged: "done",
      done: "new",
    };
    const updated = await updateFeedbackStatus(item.id, next[item.status]);
    setFeedback((prev) => prev.map((f) => (f.id === item.id ? updated : f)));
  }, []);

  const openTodos = todos.filter((t) => t.status !== "done");
  const doneTodos = todos.filter((t) => t.status === "done");

  return (
    <div className="mx-auto min-h-dvh w-full max-w-5xl bg-stone-50 px-4 py-8 text-stone-800 sm:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">于你 IT 内部工作台</h1>
        <p className="mt-1 text-sm text-stone-500">
          左边是 IT 现阶段的 todolist,右边可以直接打字或录音提需求 / 报 bug。
        </p>
      </header>

      <div className="mb-8 rounded-lg border border-stone-200 bg-white px-4 py-3 text-xs leading-relaxed text-stone-500">
        <span className="font-medium text-stone-600">怎么用:</span>
        {" "}Todolist 里点状态标签(待办/进行中/已完成)可以切换状态,新增时标题必填、详情选填,列表项右侧悬停可删除。
        提需求 / 报 Bug 选好类型,打字描述,或者点右下角麦克风直接说,系统会自动转成文字(转完还能再改),确认没问题再点提交;
        提交后会出现在下面的历史列表里,IT 处理后会把状态从"待处理"依次点成"已确认""已完成"。
      </div>

      {loadError && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {loadError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* Todo 看板 */}
        <section>
          <h2 className="mb-3 text-lg font-medium">Todolist</h2>

          <div className="mb-4 rounded-lg border border-stone-200 bg-white p-3">
            <div className="flex gap-2">
              <input
                value={newTodoTitle}
                onChange={(e) => setNewTodoTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAddTodo()}
                placeholder="新增一条待办的标题…"
                className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-stone-500"
              />
              <button
                type="button"
                onClick={handleAddTodo}
                disabled={addingTodo || !newTodoTitle.trim()}
                className="shrink-0 rounded-lg bg-stone-800 px-4 py-2 text-sm text-white disabled:opacity-40"
              >
                添加
              </button>
            </div>
            <textarea
              value={newTodoDetail}
              onChange={(e) => setNewTodoDetail(e.target.value)}
              placeholder="详细信息(选填)…"
              rows={2}
              className="mt-2 w-full resize-none rounded-lg border border-stone-200 px-3 py-1.5 text-xs outline-none focus:border-stone-500"
            />
          </div>

          {loading ? (
            <p className="text-sm text-stone-400">加载中…</p>
          ) : (
            <ul className="space-y-2">
              {openTodos.map((todo) => (
                <li
                  key={todo.id}
                  className="group flex items-start gap-3 rounded-lg border border-stone-200 bg-white px-3 py-2.5"
                >
                  <button
                    type="button"
                    onClick={() => void handleCycleStatus(todo)}
                    className={[
                      "mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                      todo.status === "in_progress"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-stone-100 text-stone-500",
                    ].join(" ")}
                    title="点击切换状态"
                  >
                    {TODO_STATUS_LABEL[todo.status]}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{todo.title}</p>
                    {todo.detail && (
                      <p className="mt-0.5 whitespace-pre-wrap text-xs text-stone-500">
                        {todo.detail}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDeleteTodo(todo.id)}
                    className="shrink-0 text-xs text-stone-300 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
                    aria-label="删除"
                  >
                    删除
                  </button>
                </li>
              ))}
              {openTodos.length === 0 && (
                <p className="text-sm text-stone-400">暂无待办 🎉</p>
              )}

              {doneTodos.length > 0 && (
                <details className="pt-2">
                  <summary className="cursor-pointer text-xs text-stone-400">
                    已完成({doneTodos.length})
                  </summary>
                  <ul className="mt-2 space-y-2">
                    {doneTodos.map((todo) => (
                      <li
                        key={todo.id}
                        className="group flex items-start gap-3 rounded-lg border border-stone-100 bg-stone-50 px-3 py-2.5 opacity-60"
                      >
                        <button
                          type="button"
                          onClick={() => void handleCycleStatus(todo)}
                          className="mt-0.5 shrink-0 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700"
                          title="点击切换状态"
                        >
                          完成
                        </button>
                        <p className="min-w-0 flex-1 text-sm line-through">{todo.title}</p>
                        <button
                          type="button"
                          onClick={() => void handleDeleteTodo(todo.id)}
                          className="shrink-0 text-xs text-stone-300 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
                        >
                          删除
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </ul>
          )}
        </section>

        {/* 提需求 / bug */}
        <section>
          <h2 className="mb-3 text-lg font-medium">提需求 / 报 Bug</h2>

          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <div className="mb-3 flex gap-2">
              <input
                value={authorName}
                onChange={(e) => setAuthorName(e.target.value)}
                placeholder="你的名字(选填)"
                className="w-32 rounded-lg border border-stone-300 px-3 py-1.5 text-sm outline-none focus:border-stone-500"
              />
              <select
                value={feedbackKind}
                onChange={(e) => setFeedbackKind(e.target.value as FeedbackKind)}
                className="rounded-lg border border-stone-300 px-2 py-1.5 text-sm outline-none focus:border-stone-500"
              >
                <option value="feature">需求</option>
                <option value="bug">Bug</option>
                <option value="other">其他</option>
              </select>
            </div>

            <textarea
              value={feedbackContent}
              onChange={(e) => setFeedbackContent(e.target.value)}
              placeholder="打字描述,或点右下角麦克风说出来,会自动转成文字…"
              rows={5}
              className="w-full resize-none rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-stone-500"
            />

            <div className="mt-3 flex items-center justify-between">
              <VoiceInputButton
                onTranscript={(text) =>
                  setFeedbackContent((prev) => (prev ? `${prev}\n${text}` : text))
                }
                onError={(msg) => setSubmitError(msg)}
                onPhaseChange={(phase) => setVoiceBusy(phase !== "idle")}
              />
              <button
                type="button"
                onClick={handleSubmitFeedback}
                disabled={submitting || voiceBusy || !feedbackContent.trim()}
                className="rounded-lg bg-stone-800 px-5 py-2 text-sm text-white disabled:opacity-40"
              >
                {submitting ? "提交中…" : "提交"}
              </button>
            </div>

            {submitError && <p className="mt-2 text-xs text-red-600">{submitError}</p>}
            {submitOk && <p className="mt-2 text-xs text-green-600">已提交,谢谢反馈!</p>}
          </div>

          <h3 className="mb-2 mt-6 text-sm font-medium text-stone-500">
            历史提交({feedback.length})
          </h3>
          <ul className="space-y-2">
            {feedback.map((item) => (
              <li
                key={item.id}
                className="rounded-lg border border-stone-200 bg-white px-3 py-2.5"
              >
                <div className="mb-1 flex items-center gap-2 text-xs text-stone-400">
                  <span className="rounded bg-stone-100 px-1.5 py-0.5">
                    {FEEDBACK_KIND_LABEL[item.kind]}
                  </span>
                  {item.author_name && <span>{item.author_name}</span>}
                  <span>{formatTime(item.created_at)}</span>
                  <button
                    type="button"
                    onClick={() => void handleCycleFeedbackStatus(item)}
                    className={[
                      "ml-auto rounded-full px-2 py-0.5 font-medium",
                      item.status === "done"
                        ? "bg-green-100 text-green-700"
                        : item.status === "triaged"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-stone-100 text-stone-600",
                    ].join(" ")}
                    title="点击切换状态"
                  >
                    {FEEDBACK_STATUS_LABEL[item.status]}
                  </button>
                </div>
                <p className="whitespace-pre-wrap text-sm">{item.content}</p>
              </li>
            ))}
            {feedback.length === 0 && !loading && (
              <p className="text-sm text-stone-400">还没有人提过需求</p>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
