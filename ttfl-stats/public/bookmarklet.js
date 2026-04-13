(function() {
  'use strict';

  // Check we're on TTFL
  if (!location.hostname.includes('trashtalk.co')) {
    alert('Ouvre ce bookmarklet sur fantasy.trashtalk.co !');
    return;
  }

  // Remove existing overlay if re-run
  var existing = document.getElementById('ttfl-stats-overlay');
  if (existing) existing.remove();

  // Parse picks from list-group-item elements
  var picks = [];
  var items = document.querySelectorAll('.list-group-item');

  items.forEach(function(item) {
    var nameEl = item.querySelector('h4.media-heading');
    var smallEl = item.querySelector('small');
    if (!nameEl || !smallEl) return;

    var playerName = nameEl.textContent.trim();
    var smallText = smallEl.textContent.trim();

    // Check for no-pick first
    if (smallText.toLowerCase().includes('no pick') || playerName.toLowerCase().includes('no pick')) {
      picks.push({ player: 'No Pick', date: smallText, score: 0, noPick: true });
      return;
    }

    // Parse score from <b>XX pts</b> inside <small>
    var boldEl = smallEl.querySelector('b');
    var score = 0;
    if (boldEl) {
      var boldMatch = boldEl.textContent.match(/(-?\d+)\s*pts?/i);
      if (boldMatch) score = parseInt(boldMatch[1], 10);
    }

    // Parse date from "Le DD-MM-YYYY pour" pattern
    var dateMatch = smallText.match(/Le\s+(\d{2}-\d{2}-\d{4})/i);
    var dateStr = dateMatch ? dateMatch[1] : '';

    // Also try format "(XX pts)" in case some entries use it
    if (!boldEl) {
      var altMatch = smallText.match(/\((-?\d+)\s*pts?\)/i);
      if (altMatch) score = parseInt(altMatch[1], 10);
    }

    picks.push({ player: playerName, date: dateStr, score: score });
  });

  // Parse total points and rank from profile stats
  var statCounts = document.querySelectorAll('.profile-stat-count');
  var totalPoints = statCounts[0] ? parseInt(statCounts[0].textContent.replace(/\s/g, ''), 10) : null;
  var rank = statCounts[1] ? statCounts[1].textContent.trim() : null;

  // Get username
  var usernameEl = document.querySelector('.profile-usertitle-name h2, .profile-usertitle h2');
  var username = usernameEl ? usernameEl.textContent.trim() : 'Joueur';

  // Compute stats
  var realPicks = picks.filter(function(p) { return !p.noPick; });
  var scores = realPicks.map(function(p) { return p.score; });
  var noPicks = picks.filter(function(p) { return p.noPick; }).length;

  var avg = scores.length ? (scores.reduce(function(a, b) { return a + b; }, 0) / scores.length) : 0;
  var best = scores.length ? Math.max.apply(null, scores) : 0;
  var worst = scores.length ? Math.min.apply(null, scores) : 0;
  var bestPick = realPicks.find(function(p) { return p.score === best; });
  var worstPick = realPicks.find(function(p) { return p.score === worst; });

  // Score distribution
  var above60 = scores.filter(function(s) { return s >= 60; }).length;
  var above40 = scores.filter(function(s) { return s >= 40 && s < 60; }).length;
  var above20 = scores.filter(function(s) { return s >= 20 && s < 40; }).length;
  var below20 = scores.filter(function(s) { return s < 20; }).length;
  var negative = scores.filter(function(s) { return s < 0; }).length;

  // Streak: current consecutive positive scores
  var streak = 0;
  for (var i = 0; i < scores.length; i++) {
    if (scores[i] >= 30) streak++;
    else break;
  }

  // Last 10 trend
  var last10 = scores.slice(0, 10);
  var avgL10 = last10.length ? (last10.reduce(function(a, b) { return a + b; }, 0) / last10.length) : 0;
  var trendIcon = avgL10 > avg ? '📈' : avgL10 < avg * 0.9 ? '📉' : '➡️';

  // Build overlay
  var overlay = document.createElement('div');
  overlay.id = 'ttfl-stats-overlay';
  overlay.innerHTML = [
    '<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);z-index:999999;overflow-y:auto;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#e2e8f0">',
    '<div style="max-width:480px;margin:20px auto;padding:20px">',

    // Header
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">',
    '<div><h1 style="font-size:22px;font-weight:bold;margin:0;color:#f59e0b">🏀 TTFL Stats</h1>',
    '<p style="color:#94a3b8;font-size:13px;margin:4px 0 0">' + username + (rank ? ' · Classement : ' + rank : '') + '</p></div>',
    '<button id="ttfl-stats-close" style="background:none;border:none;color:#94a3b8;font-size:28px;cursor:pointer;padding:0">✕</button>',
    '</div>',

    // Main stats
    '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">',
    '<div style="background:#1e293b;border-radius:10px;padding:12px;text-align:center">',
    '<div style="font-size:24px;font-weight:bold;color:#10b981">' + (totalPoints || scores.reduce(function(a,b){return a+b},0)) + '</div>',
    '<div style="font-size:11px;color:#64748b">Total pts</div></div>',
    '<div style="background:#1e293b;border-radius:10px;padding:12px;text-align:center">',
    '<div style="font-size:24px;font-weight:bold">' + realPicks.length + '</div>',
    '<div style="font-size:11px;color:#64748b">Picks</div></div>',
    '<div style="background:#1e293b;border-radius:10px;padding:12px;text-align:center">',
    '<div style="font-size:24px;font-weight:bold;color:#3b82f6">' + avg.toFixed(1) + '</div>',
    '<div style="font-size:11px;color:#64748b">Moyenne</div></div>',
    '</div>',

    // Best / Worst
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">',
    '<div style="background:#1a2e1a;border:1px solid #166534;border-radius:10px;padding:12px">',
    '<div style="font-size:11px;color:#10b981;font-weight:bold;margin-bottom:4px">🔥 MEILLEUR PICK</div>',
    '<div style="font-size:18px;font-weight:bold;color:#10b981">' + best + ' pts</div>',
    '<div style="font-size:12px;color:#94a3b8">' + (bestPick ? bestPick.player : '-') + '</div>',
    '<div style="font-size:11px;color:#64748b">' + (bestPick ? bestPick.date : '') + '</div></div>',
    '<div style="background:#2d1f1f;border:1px solid #991b1b;border-radius:10px;padding:12px">',
    '<div style="font-size:11px;color:#ef4444;font-weight:bold;margin-bottom:4px">💀 PIRE PICK</div>',
    '<div style="font-size:18px;font-weight:bold;color:#ef4444">' + worst + ' pts</div>',
    '<div style="font-size:12px;color:#94a3b8">' + (worstPick ? worstPick.player : '-') + '</div>',
    '<div style="font-size:11px;color:#64748b">' + (worstPick ? worstPick.date : '') + '</div></div>',
    '</div>',

    // Tendance + Streak
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">',
    '<div style="background:#1e293b;border-radius:10px;padding:12px">',
    '<div style="font-size:11px;color:#64748b;margin-bottom:4px">Tendance L10</div>',
    '<div style="font-size:20px;font-weight:bold">' + trendIcon + ' ' + avgL10.toFixed(1) + '</div>',
    '<div style="font-size:11px;color:#64748b">vs ' + avg.toFixed(1) + ' saison</div></div>',
    '<div style="background:#1e293b;border-radius:10px;padding:12px">',
    '<div style="font-size:11px;color:#64748b;margin-bottom:4px">Série en cours</div>',
    '<div style="font-size:20px;font-weight:bold">' + (streak > 0 ? '🔥 ' + streak + ' picks' : '—') + '</div>',
    '<div style="font-size:11px;color:#64748b">consécutifs ≥ 30 pts</div></div>',
    '</div>',

    // Distribution
    '<div style="background:#1e293b;border-radius:10px;padding:14px;margin-bottom:16px">',
    '<div style="font-size:12px;color:#64748b;font-weight:bold;margin-bottom:10px">DISTRIBUTION DES SCORES</div>',
    buildBar('60+ pts', above60, scores.length, '#10b981'),
    buildBar('40-59 pts', above40, scores.length, '#3b82f6'),
    buildBar('20-39 pts', above20, scores.length, '#f59e0b'),
    buildBar('0-19 pts', below20, scores.length, '#f97316'),
    buildBar('Négatif', negative, scores.length, '#ef4444'),
    '</div>',

    // No picks
    noPicks > 0 ? '<div style="background:#2d1f1f;border-radius:10px;padding:10px;margin-bottom:16px;text-align:center;font-size:13px;color:#ef4444">⚠️ ' + noPicks + ' no-pick' + (noPicks > 1 ? 's' : '') + ' cette saison</div>' : '',

    // Top 5 picks
    '<div style="background:#1e293b;border-radius:10px;padding:14px;margin-bottom:16px">',
    '<div style="font-size:12px;color:#64748b;font-weight:bold;margin-bottom:10px">TOP 5 PICKS</div>',
    realPicks.slice().sort(function(a,b){return b.score-a.score}).slice(0,5).map(function(p,i){
      return '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #0f172a;font-size:13px">' +
        '<span style="color:#94a3b8">' + (i+1) + '. ' + p.player + '</span>' +
        '<span style="color:#10b981;font-weight:bold">' + p.score + '</span></div>';
    }).join(''),
    '</div>',

    // Worst 5 picks
    '<div style="background:#1e293b;border-radius:10px;padding:14px;margin-bottom:16px">',
    '<div style="font-size:12px;color:#64748b;font-weight:bold;margin-bottom:10px">FLOP 5 PICKS</div>',
    realPicks.slice().sort(function(a,b){return a.score-b.score}).slice(0,5).map(function(p,i){
      return '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #0f172a;font-size:13px">' +
        '<span style="color:#94a3b8">' + (i+1) + '. ' + p.player + '</span>' +
        '<span style="color:#ef4444;font-weight:bold">' + p.score + '</span></div>';
    }).join(''),
    '</div>',

    // Footer
    '<div style="text-align:center;color:#475569;font-size:11px;padding:10px">TTFL Stats Bookmarklet · Powered by TTFL Advisor</div>',

    '</div></div>'
  ].join('');

  document.body.appendChild(overlay);
  document.getElementById('ttfl-stats-close').addEventListener('click', function() {
    overlay.remove();
  });

  // Close on Escape
  document.addEventListener('keydown', function handler(e) {
    if (e.key === 'Escape') {
      overlay.remove();
      document.removeEventListener('keydown', handler);
    }
  });

  function buildBar(label, count, total, color) {
    var pct = total > 0 ? (count / total * 100) : 0;
    return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px">' +
      '<span style="min-width:70px;color:#94a3b8">' + label + '</span>' +
      '<div style="flex:1;background:#0f172a;border-radius:4px;height:18px;overflow:hidden">' +
      '<div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:4px;min-width:' + (count > 0 ? '2px' : '0') + '"></div></div>' +
      '<span style="min-width:30px;text-align:right;color:#e2e8f0">' + count + '</span></div>';
  }
})();
