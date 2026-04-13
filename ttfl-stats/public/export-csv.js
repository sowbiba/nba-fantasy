(function() {
  'use strict';

  if (!location.hostname.includes('trashtalk.co')) {
    alert('Ouvre ce bookmarklet sur fantasy.trashtalk.co !');
    return;
  }

  // Find the DataTable
  var table = document.getElementById('MuTabme');
  if (!table) {
    table = document.querySelector('table.dataTable, table.table');
  }
  if (!table) {
    alert('Aucun tableau trouvé. Va sur la page Historique des decks (?tpl=historique).');
    return;
  }

  // Try to get ALL rows from DataTable API (not just visible page)
  var allRows = [];
  var headerRow = [];

  // Parse headers
  var ths = table.querySelectorAll('thead th');
  ths.forEach(function(th) {
    headerRow.push(th.textContent.trim());
  });

  // Check if jQuery DataTable API is available
  if (window.jQuery && jQuery.fn.DataTable && jQuery(table).DataTable) {
    try {
      var dt = jQuery(table).DataTable();
      var data = dt.rows().data();
      for (var i = 0; i < data.length; i++) {
        var row = [];
        for (var j = 0; j < data[i].length; j++) {
          // Strip HTML tags
          var cellText = String(data[i][j]).replace(/<[^>]*>/g, '').trim();
          row.push(cellText);
        }
        allRows.push(row);
      }
    } catch (e) {
      // Fallback to DOM parsing
      allRows = [];
    }
  }

  // Fallback: parse all visible rows from DOM
  if (allRows.length === 0) {
    var trs = table.querySelectorAll('tbody tr');
    trs.forEach(function(tr) {
      var row = [];
      tr.querySelectorAll('td').forEach(function(td) {
        row.push(td.textContent.trim().replace(/\s+/g, ' '));
      });
      if (row.length > 0) allRows.push(row);
    });
  }

  if (allRows.length === 0) {
    alert('Pas de données à exporter.');
    return;
  }

  // Build CSV
  function escapeCSV(val) {
    val = String(val);
    if (val.indexOf(',') !== -1 || val.indexOf('"') !== -1 || val.indexOf('\n') !== -1) {
      return '"' + val.replace(/"/g, '""') + '"';
    }
    return val;
  }

  var csvLines = [];
  if (headerRow.length > 0) {
    csvLines.push(headerRow.map(escapeCSV).join(','));
  }
  allRows.forEach(function(row) {
    csvLines.push(row.map(escapeCSV).join(','));
  });

  // Download
  var csv = '\uFEFF' + csvLines.join('\n');
  var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  var url = URL.createObjectURL(blob);

  var link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', 'ttfl-historique-' + new Date().toISOString().split('T')[0] + '.csv');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  // Toast
  var dtWarning = (window.jQuery && jQuery(table).DataTable) ? '' : ' (page visible uniquement)';
  var toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#10b981;color:#0f172a;padding:12px 24px;border-radius:10px;font-weight:bold;font-size:14px;z-index:999999;font-family:-apple-system,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.3)';
  toast.textContent = '✅ CSV exporté ! ' + allRows.length + ' lignes' + dtWarning;
  document.body.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 4000);
})();
