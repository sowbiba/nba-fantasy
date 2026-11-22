import ScoreByDay, { scoreByDayMetadata } from "@/components/ScoreByDay";

// Scores TTFL par soirée, saison 2025-26 (voir components/ScoreByDay).
export const dynamic = "force-dynamic";

export const metadata = scoreByDayMetadata("2025-26");

export default function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  return <ScoreByDay season="2025-26" searchParams={searchParams} />;
}
