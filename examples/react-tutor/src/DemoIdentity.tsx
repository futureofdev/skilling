import { useEffect, useState } from "react";
import { App } from "./App";

type Identity = {
  enabled: boolean;
  label?: string;
  selected?: string | null;
  choices?: { selector: string; label: string }[];
};

/** Local demonstration only; deployed applications supply server-authenticated identity. */
export function DemoIdentity() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    let active = true;
    fetch("/api/demo", { credentials: "same-origin" })
      .then(async response => {
        if (!response.ok) throw new Error("The tutor could not load. Check that the server is running.");
        const value: Identity = await response.json();
        if (active) setIdentity(value);
      })
      .catch(error => { if (active) setProblem(String(error.message)); });
    return () => { active = false; };
  }, []);
  async function select(selector: string) {
    setBusy(true);
    setProblem("");
    try {
      const response = await fetch("/api/demo/select", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selector }),
      });
      if (!response.ok) throw new Error("That learner could not be selected. Reload and try again.");
      const result: { selected: string } = await response.json();
      setIdentity(current => current ? { ...current, selected: result.selected } : current);
      setGeneration(value => value + 1);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "Selection failed.");
    } finally {
      setBusy(false);
    }
  }
  if (!identity) return <main className="demo-identity" aria-live="polite">{problem || "Opening your tutor…"}</main>;
  return <>
    {identity.enabled && (identity.choices?.length || 0) > 1 && <section className="demo-identity" aria-label="Demo learner">
      <span>{identity.label}</span>
      <label> Learner <select aria-label="Demo learner" disabled={busy} value={identity.choices?.find(item => item.label === identity.selected)?.selector || ""} onChange={event => void select(event.target.value)}>
        <option value="" disabled>Select a learner</option>
        {identity.choices?.map(item => <option key={item.selector} value={item.selector}>{item.label}</option>)}
      </select></label>
      {problem && <p role="alert">{problem}</p>}
    </section>}
    {(!identity.enabled || identity.selected) && !busy && <App key={generation} />}
  </>;
}
