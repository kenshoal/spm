"use client";

import { useActionState, useState } from "react";
import {
  DESCRIPTION_MAX,
  SKILL_TAGS,
  SKILL_TAG_LABELS,
  descriptionLength,
} from "@/lib/technical-support-options";
import {
  recordSupportRequirement,
  type TechnicalSupportActionState,
} from "./technical-support-actions";

const initialState: TechnicalSupportActionState = {};

// AC1-X3: the description is bounded where it is typed — the submit stays
// disabled until the text is 1–2000 characters and one of the four skills is
// chosen, so a dead form can never post a payload the API must refuse.
export function RequirementForm({ eventRequestId }: { eventRequestId: string }) {
  const [description, setDescription] = useState("");
  const [skillTag, setSkillTag] = useState("");
  // The fields are controlled, so React's automatic form reset does not clear
  // them; clear them on success so a second click cannot record a duplicate.
  // A refusal keeps the text for the coordinator to correct.
  const [state, formAction, isPending] = useActionState(
    async (previousState: TechnicalSupportActionState, formData: FormData) => {
      const result = await recordSupportRequirement(previousState, formData);
      if (!result.message) {
        setDescription("");
        setSkillTag("");
      }
      return result;
    },
    initialState,
  );
  // Counted as the API and database count it: trimmed, in characters.
  const length = descriptionLength(description);
  const overLimit = length > DESCRIPTION_MAX;
  const descriptionValid = length >= 1 && !overLimit;
  const skillValid = (SKILL_TAGS as readonly string[]).includes(skillTag);
  return (
    <form action={formAction} className="mt-4 rounded-xl border border-[#e1e7e4] p-4">
      <input type="hidden" name="event_request_id" value={eventRequestId} />
      <label htmlFor="support-description" className="block text-sm font-semibold text-[#1b2b25]">
        What support is needed?
      </label>
      <textarea
        id="support-description"
        name="description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        rows={3}
        className="mt-1 w-full rounded-lg border border-[#cfd9d4] px-3 py-2 text-sm text-[#1b2b25]"
      />
      <div className="mt-1 flex items-baseline justify-between gap-3">
        {length === 0 ? (
          <p className="text-sm text-[#718078]">Describe the support needed</p>
        ) : state.message ? (
          <p role="alert" className="text-sm text-[#a23939]">{state.message}</p>
        ) : null}
        <p
          aria-live="polite"
          data-error={overLimit ? "true" : undefined}
          className={`text-xs ${overLimit ? "text-[#a23939]" : "text-[#718078]"}`}
        >
          {length}/{DESCRIPTION_MAX}
        </p>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="support-skill" className="block text-sm font-semibold text-[#1b2b25]">
            Skill
          </label>
          <select
            id="support-skill"
            name="skill_tag"
            value={skillTag}
            onChange={(event) => setSkillTag(event.target.value)}
            className="mt-1 min-h-11 rounded-lg border border-[#cfd9d4] bg-white px-3 text-sm text-[#1b2b25]"
          >
            <option value="">Select a skill</option>
            {SKILL_TAGS.map((tag) => (
              <option key={tag} value={tag}>
                {SKILL_TAG_LABELS[tag]}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={isPending || !descriptionValid || !skillValid}
          className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white hover:bg-[#0c584b] disabled:opacity-60"
        >
          {isPending ? "Recording…" : "Record requirement"}
        </button>
      </div>
    </form>
  );
}
