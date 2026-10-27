export type TranscriptSegment = {
  text: string;
  startSeconds: number;
  endSeconds: number;
};

export function readSegments(raw: unknown[] | null): TranscriptSegment[] {
  if (!raw) {
    return [];
  }

  return raw.flatMap((item) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }

    const record = item as Record<string, unknown>;
    if (
      typeof record.text !== "string" ||
      typeof record.start_seconds !== "number" ||
      typeof record.end_seconds !== "number"
    ) {
      return [];
    }

    return [
      {
        text: record.text,
        startSeconds: record.start_seconds,
        endSeconds: record.end_seconds,
      },
    ];
  });
}
