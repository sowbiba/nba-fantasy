import ScoreByDay, { scoreByDayMetadata } from "@/components/ScoreByDay";

// Scores TTFL par soirée, saison 2026-27 (voir components/ScoreByDay).
export const dynamic = "force-dynamic";

export const metadata = scoreByDayMetadata("2026-27");

export default function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  return <ScoreByDay season="2026-27" searchParams={searchParams} />;
}
