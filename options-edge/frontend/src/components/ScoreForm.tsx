"use client";

import { useState } from "react";
import { thesesApi, type UserScore } from "@/lib/api";

interface Props {
  thesisId: string;
  existingScore: UserScore | null;
  onSaved: () => void;
}

export default function ScoreForm({ thesisId, existingScore, onSaved }: Props) {
  const [score, setScore] = useState(existingScore?.score ?? 5);
  const [directionCorrect, setDirectionCorrect] = useState<boolean | null>(
    existingScore?.direction_correct ?? null
  );
  const [structureAppropriate, setStructureAppropriate] = useState<boolean | null>(
    existingScore?.structure_appropriate ?? null
  );
  const [timingGood, setTimingGood] = useState<boolean | null>(
    existingScore?.timing_good ?? null
  );
  const [notes, setNotes] = useState(existingScore?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await thesesApi.submitUserScore(thesisId, {
        score,
        direction_correct: directionCorrect ?? undefined,
        structure_appropriate: structureAppropriate ?? undefined,
        timing_good: timingGood ?? undefined,
        notes: notes || undefined,
      });
      setSaved(true);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  function TriState({
    label,
    value,
    onChange,
  }: {
    label: string;
    value: boolean | null;
    onChange: (v: boolean | null) => void;
  }) {
    return (
      <div>
        <div className="text-xs text-slate-500 mb-1">{label}</div>
        <div className="flex gap-2">
          {([true, false, null] as const).map((v) => (
            <button
              key={String(v)}
              onClick={() => onChange(v)}
              className={`px-2 py-1 rounded text-xs font-medium border transition-colors ${
                value === v
                  ? v === true
                    ? "bg-green-100 border-green-300 text-green-700"
                    : v === false
                    ? "bg-red-100 border-red-300 text-red-700"
                    : "bg-slate-200 border-slate-300 text-slate-600"
                  : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"
              }`}
            >
              {v === true ? "Yes" : v === false ? "No" : "—"}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h2 className="font-semibold text-slate-800 mb-4">
        {existingScore ? "Edit Your Score" : "Score This Thesis"}
      </h2>

      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm text-slate-600">Overall Score</label>
            <span className="text-lg font-bold text-slate-900">{score}/10</span>
          </div>
          <input
            type="range"
            min={1}
            max={10}
            value={score}
            onChange={(e) => setScore(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div className="flex flex-wrap gap-6">
          <TriState label="Direction Correct?" value={directionCorrect} onChange={setDirectionCorrect} />
          <TriState label="Structure Appropriate?" value={structureAppropriate} onChange={setStructureAppropriate} />
          <TriState label="Timing Good?" value={timingGood} onChange={setTimingGood} />
        </div>

        <div>
          <label className="block text-sm text-slate-600 mb-1">Notes</label>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What worked? What didn't?"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving..." : saved ? "Saved!" : "Save Score"}
        </button>
      </div>
    </div>
  );
}
