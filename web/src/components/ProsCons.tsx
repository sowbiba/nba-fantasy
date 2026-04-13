export function ProsBlock({ pros }: { pros: string[] }) {
  return (
    <div className="bg-green-950/50 border border-green-800 rounded-xl p-3">
      <h3 className="text-green-500 font-bold text-sm mb-1.5">✅ POUR</h3>
      <ul className="text-gray-300 text-sm leading-relaxed list-disc list-inside space-y-1">
        {pros.map((p, i) => (<li key={i}>{p}</li>))}
      </ul>
    </div>
  );
}

export function ConsBlock({ cons }: { cons: string[] }) {
  return (
    <div className="bg-red-950/50 border border-red-900 rounded-xl p-3">
      <h3 className="text-red-400 font-bold text-sm mb-1.5">❌ CONTRE</h3>
      <ul className="text-gray-300 text-sm leading-relaxed list-disc list-inside space-y-1">
        {cons.map((c, i) => (<li key={i}>{c}</li>))}
      </ul>
    </div>
  );
}

export function VerdictBlock({ verdict }: { verdict: string }) {
  return (
    <div className="bg-gray-900 border border-amber-800 rounded-xl p-3">
      <h3 className="text-amber-500 font-bold text-sm mb-1.5">💡 VERDICT</h3>
      <p className="text-gray-100 text-sm leading-relaxed">{verdict}</p>
    </div>
  );
}
