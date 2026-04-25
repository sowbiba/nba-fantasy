export function computeTtflScore(stats: {
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  fgm: number;
  fga: number;
  tpm: number;
  tpa: number;
  ftm: number;
  fta: number;
  tov: number;
}): number {
  const positive =
    stats.pts +
    stats.reb +
    stats.ast +
    stats.stl +
    stats.blk +
    stats.fgm +
    stats.tpm +
    stats.ftm;
  const negative =
    stats.tov +
    (stats.fga - stats.fgm) +
    (stats.tpa - stats.tpm) +
    (stats.fta - stats.ftm);
  return positive - negative;
}
