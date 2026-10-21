"use client";

import { useState } from "react";
import { uiText } from "@/lib/i18n";
import type { AgentClarification, ClarificationReply } from "@/lib/ai";

export default function ClarificationCard({ question, disabled, submit }: {
  question: AgentClarification;
  disabled: boolean;
  submit: (text: string, reply: ClarificationReply) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  return <form className="ai-clarification" onSubmit={(event) => {
    event.preventDefault();
    const text = question.questions.map((item) => item.question + "：" + answers[item.id]).join("\n");
    submit(text, { clarification_id: question.id, answers });
  }}>
    <strong>{uiText("补充规划信息")}</strong>
    {question.questions.map((item) => <fieldset key={item.id} disabled={disabled}>
      <legend>{item.question}</legend>
      {item.options.length > 0 && <div className="ai-question-options" role="group" aria-label={item.question}>
        {item.options.map((option) => <button type="button" key={option}
          aria-pressed={answers[item.id] === option}
          onClick={() => setAnswers((old) => ({ ...old, [item.id]: option }))}>
          {option}
        </button>)}
      </div>}
      <input aria-label={item.question} value={answers[item.id] || ""} required maxLength={2000}
        placeholder={uiText("选择选项，或输入你的答案")}
        onChange={(event) => setAnswers((old) => ({ ...old, [item.id]: event.target.value }))} />
    </fieldset>)}
    <button className="button primary" disabled={disabled || question.questions.some((item) => !answers[item.id]?.trim())}>
      {uiText("提交并继续规划")}
    </button>
  </form>;
}
