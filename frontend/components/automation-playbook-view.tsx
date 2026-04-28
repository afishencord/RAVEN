"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { NodeAutomationAssignments } from "@/lib/types";

type Props = {
  assignments: NodeAutomationAssignments;
  executionMode: string;
};

export function AutomationPlaybookView({ assignments, executionMode }: Props) {
  const laneRef = useRef<HTMLDivElement | null>(null);
  const validationRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const remediationRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [validationCenters, setValidationCenters] = useState<Record<number, number>>({});
  const [remediationCenters, setRemediationCenters] = useState<Record<number, number>>({});

  const validations = useMemo(
    () => [...assignments.validations].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [assignments.validations],
  );
  const remediations = useMemo(
    () => [...assignments.remediations].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [assignments.remediations],
  );
  const validationIds = useMemo(() => new Set(validations.map((item) => item.validation_id)), [validations]);
  const remediationIds = useMemo(() => new Set(remediations.map((item) => item.remediation_id)), [remediations]);
  const validEdges = useMemo(
    () =>
      [...(assignments.edges ?? [])]
        .filter((edge) => edge.is_enabled && validationIds.has(edge.validation_id) && remediationIds.has(edge.remediation_id))
        .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [assignments.edges, remediationIds, validationIds],
  );

  useEffect(() => {
    function measureCenters() {
      const lane = laneRef.current;
      if (!lane) {
        return;
      }
      const laneRect = lane.getBoundingClientRect();
      const nextValidationCenters: Record<number, number> = {};
      const nextRemediationCenters: Record<number, number> = {};
      for (const assignment of validations) {
        const element = validationRefs.current[assignment.validation_id];
        if (element) {
          const rect = element.getBoundingClientRect();
          nextValidationCenters[assignment.validation_id] = rect.top + rect.height / 2 - laneRect.top;
        }
      }
      for (const assignment of remediations) {
        const element = remediationRefs.current[assignment.remediation_id];
        if (element) {
          const rect = element.getBoundingClientRect();
          nextRemediationCenters[assignment.remediation_id] = rect.top + rect.height / 2 - laneRect.top;
        }
      }
      setValidationCenters(nextValidationCenters);
      setRemediationCenters(nextRemediationCenters);
    }

    measureCenters();
    window.addEventListener("resize", measureCenters);
    return () => window.removeEventListener("resize", measureCenters);
  }, [validations, remediations]);

  function yFor(kind: "validation" | "remediation", id: number) {
    if (kind === "validation") {
      return validationCenters[id] ?? 64 + Math.max(validations.findIndex((item) => item.validation_id === id), 0) * 96;
    }
    return remediationCenters[id] ?? 64 + Math.max(remediations.findIndex((item) => item.remediation_id === id), 0) * 96;
  }

  return (
    <div className="mt-5 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
      <div className="flex flex-col gap-3 border-b border-slate-200 bg-panel px-5 py-4 dark:border-slate-800 dark:bg-[#0B1020] sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {validations.length} validations, {remediations.length} remediations, {validEdges.length} connections
        </p>
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{executionMode} execution path</p>
      </div>

      <div className="relative min-h-[28rem] overflow-auto bg-white p-5 dark:bg-[#050814]">
        <div className="grid min-w-[44rem] grid-cols-[1fr_8rem_1fr] gap-y-4">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Validations</p>
            <div className="space-y-4">
              {validations.map((assignment) => (
                <div
                  key={assignment.id}
                  ref={(element) => {
                    validationRefs.current[assignment.validation_id] = element;
                  }}
                  className="relative rounded-2xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]"
                >
                  <span className="absolute -right-3 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full border border-white bg-[#7C3AED] text-white shadow-sm dark:border-[#050814]">
                    <span className="h-2 w-2 rounded-full bg-white" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{assignment.validation.name}</p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {assignment.validation.validation_type} | {assignment.validation.is_enabled ? "enabled" : "disabled"}
                    </p>
                    {assignment.validation.expected_response_contains ? (
                      <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{assignment.validation.expected_response_contains}</p>
                    ) : null}
                  </div>
                </div>
              ))}
              {!validations.length ? (
                <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  No validations are assigned to this node.
                </p>
              ) : null}
            </div>
          </div>

          <div ref={laneRef} className="relative min-h-[22rem]">
            <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible" preserveAspectRatio="none">
              {validEdges.map((edge) => {
                const fromY = yFor("validation", edge.validation_id);
                const toY = yFor("remediation", edge.remediation_id);
                return (
                  <g key={`${edge.validation_id}:${edge.remediation_id}`}>
                    <path d={`M 12 ${fromY} C 46 ${fromY}, 82 ${toY}, 116 ${toY}`} stroke="#C4B5FD" strokeWidth="7" strokeLinecap="round" fill="none" opacity="0.55" />
                    <path d={`M 12 ${fromY} C 46 ${fromY}, 82 ${toY}, 116 ${toY}`} stroke="#7C3AED" strokeWidth="3" strokeLinecap="round" fill="none" />
                    <circle cx="12" cy={fromY} r="6" fill="#7C3AED" />
                    <circle cx="116" cy={toY} r="6" fill="#7C3AED" />
                  </g>
                );
              })}
            </svg>
            {validations.length > 0 && remediations.length > 0 && !validEdges.length ? (
              <div className="absolute inset-x-0 top-8 z-0 rounded-2xl border border-dashed border-slate-300 px-3 py-4 text-center text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
                No connector paths configured.
              </div>
            ) : null}
          </div>

          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Remediations</p>
            <div className="space-y-4">
              {remediations.map((assignment) => {
                const connectedValidationNames = validEdges
                  .filter((edge) => edge.remediation_id === assignment.remediation_id)
                  .map((edge) => validations.find((item) => item.validation_id === edge.validation_id)?.validation.name ?? `Validation ${edge.validation_id}`);
                return (
                  <div
                    key={assignment.id}
                    ref={(element) => {
                      remediationRefs.current[assignment.remediation_id] = element;
                    }}
                    className="relative rounded-2xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]"
                  >
                    <span className="absolute -left-3 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full border border-white bg-[#7C3AED] text-white shadow-sm dark:border-[#050814]">
                      <span className="h-2 w-2 rounded-full bg-white" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{assignment.remediation.name}</p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        {assignment.remediation.risk_level} risk | {assignment.remediation.is_enabled ? "enabled" : "disabled"}
                      </p>
                      <p className="mt-2 line-clamp-2 font-mono text-xs text-slate-500 dark:text-slate-400">{assignment.remediation.command}</p>
                    </div>
                    {connectedValidationNames.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {connectedValidationNames.map((name, index) => (
                          <span key={`${name}:${index}`} className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-[#050814] dark:text-slate-300">
                            {name}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {!remediations.length ? (
                <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  No remediations are assigned to this node.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
