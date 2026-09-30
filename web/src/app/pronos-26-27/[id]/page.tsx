import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getClosure, getPronoCore } from "../core";
import PronoEditor from "../PronoEditor";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Pronos NBA 2026-27",
  robots: { index: false, follow: false },
};

export default async function PronoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [prono, closure] = await Promise.all([getPronoCore(id), getClosure()]);
  if (!prono) notFound();

  return (
    <PronoEditor key={prono.id} id={prono.id} name={prono.name} initialWins={prono.wins} closed={closure.closed} />
  );
}
