// ═══════════════════════════════════════════════════════════════════════════
// briefing.js  —  Fantasy Baseball Daily Briefing frontend
// ═══════════════════════════════════════════════════════════════════════════

// ── Global constants and state ──────────────────────────────────────────────
// FDB_YEAR is injected by the Python renderer from settings.py.
// Fallback to current year if not already defined (e.g. standalone testing).
if (typeof FDB_YEAR === 'undefined') { var FDB_YEAR = new Date().getFullYear(); }
var BAT_SC     = { R:1, HR:1, TB:1, RBI:1, BB:1, SB:1, K:-1 };
var PIT_SC     = { IP:3, H:-1, ER:-2, HR:-1, BB:-1, K:1, QS:2, W:2, L:-2, SV:6, BS:-3, HD:5, SVHD:2 };

// Player-modal state
var _mlbamCache  = {};
var _pmName      = '';
var _pmIsp       = false;
var _pmMlbam     = '';

// News tab state
var _newsCache   = null;
var _newsLoading = false;

// ── Tab switcher (single consolidated function — replaces three-layer override chain) ──
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(
    b => b.classList.toggle('active', b.dataset.tab === tab)
  );
  document.querySelectorAll('.tab-pane').forEach(
    p => p.style.display = p.dataset.tab === tab ? 'block' : 'none'
  );
  try { localStorage.setItem('fdb_tab', tab); } catch (e) {}

  // Per-tab side effects
  if (tab === 'today') loadNewsTab();   // auto-load news banner in Today tab

  // Re-wire player-name click handlers after dynamic content renders
  setTimeout(_wireAllPlayerNames, 150);
}
function toggleTheme() {
  var el   = document.documentElement;
  var next = el.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  el.setAttribute('data-theme', next);
  try { localStorage.setItem('fdb_theme', next); } catch (e) {}
  document.getElementById('theme-icon').textContent =
    next === 'dark' ? '\u2600\ufe0f' : '\ud83c\udf19';
}

// ── Theme & tab restore on page load ───────────────────────────────────────
window.addEventListener('DOMContentLoaded', function () {
  var saved = 'dark';
  try { saved = localStorage.getItem('fdb_theme') || 'dark'; } catch (e) {}
  document.documentElement.setAttribute('data-theme', saved);
  document.getElementById('theme-icon').textContent =
    saved === 'dark' ? '\u2600\ufe0f' : '\ud83c\udf19';

  var tab = 'today';
  try { tab = localStorage.getItem('fdb_tab') || 'today'; } catch (e) {}
  // Remap legacy tab names to new nav structure
  var _tabMap = {matchup:'today', waivers:'today', news:'today',
                 league:'myteam', analytics:'tools', lineuplab:'tools',
                 seasonpace:'tools', trade:'tools'};
  tab = _tabMap[tab] || tab;
  switchTab(tab);
});

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') closePlayerModal();
});

function closePlayerModal() {
  document.getElementById('player-modal').style.display = 'none';
  document.body.style.overflow = '';
}

function buildYearOptions() {
  var opts = '';
  for (var y = FDB_YEAR; y >= 2020; y--) {
    opts += '<option value="' + y + '"' + (y === FDB_YEAR ? ' selected' : '') + '>' + y + '</option>';
  }
  return opts;
}

function changeModalYear(year) {
  year = parseInt(year, 10);
  var w = document.getElementById('pm-log-wrap');
  if (w) w.innerHTML = '<div class="pm-loading">Loading\u2026</div>';
  var mid = _mlbamCache[_pmName] || _pmMlbam;
  fetchGameLog(mid, _pmIsp, _pmName, year);
}

function loadNewsTab() {
  if (_newsCache !== null || _newsLoading) return;
  _newsLoading = true;
  var wrap = document.getElementById('news-list-wrap');
  if (wrap) wrap.innerHTML = '<div class="news-loading">Loading roster news\u2026</div>';
  if (!window.FDB_ROSTER || !FDB_ROSTER.length) {
    if (wrap) wrap.innerHTML = '<div class="news-empty">No roster players found.</div>';
    _newsLoading = false;
    _newsCache   = [];
    return;
  }
  fetchPlayerNews(FDB_ROSTER, 0, []);
}

function fetchPlayerNews(players, idx, allItems) {
  if (idx >= players.length) {
    _newsLoading = false;
    _newsCache   = allItems;
    renderNews(allItems);
    return;
  }
  var p = players[idx];

  function next() {
    setTimeout(function () { fetchPlayerNews(players, idx + 1, allItems); }, 75);
  }

  function proceed(mid) {
    if (!mid) { next(); return; }
    var grp = p.isp ? 'pitching' : 'hitting';
    var url = 'https://statsapi.mlb.com/api/v1/people/' + mid +
              '/stats?stats=gameLog&season=' + FDB_YEAR + '&group=' + grp;
    fetch(url, {signal: AbortSignal.timeout(8000)})
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var sp = (data.stats && data.stats[0] && data.stats[0].splits) || [];
        if (sp.length) {
          detectNewsItems(sp, p).forEach(function (it) { allItems.push(it); });
          next();
        } else {
          var url2 = 'https://statsapi.mlb.com/api/v1/people/' + mid +
                     '/stats?stats=gameLog&season=' + (FDB_YEAR - 1) + '&group=' + grp;
          fetch(url2, {signal: AbortSignal.timeout(8000)})
            .then(function (r2) { return r2.json(); })
            .then(function (d2) {
              var sp2 = (d2.stats && d2.stats[0] && d2.stats[0].splits) || [];
              detectNewsItems(sp2, p).forEach(function (it) { allItems.push(it); });
              next();
            })
            .catch(function (err) { console.warn('News fallback fetch failed:', err); next(); });
        }
      })
      .catch(function (err) { console.warn('News fetch failed:', err); next(); });
  }

  if (p.mlbam) {
    _mlbamCache[p.name] = p.mlbam;
    proceed(p.mlbam);
  } else if (_mlbamCache[p.name]) {
    proceed(_mlbamCache[p.name]);
  } else {
    var surl = 'https://statsapi.mlb.com/api/v1/people/search?names=' +
               encodeURIComponent(p.name) + '&sportId=1';
    fetch(surl)
      .then(function (r) { return r.json(); })
      .then(function (sd) {
        var ppl = (sd.people || []).filter(function (x) { return x.active !== false; });
        if (!ppl.length) ppl = sd.people || [];
        if (ppl.length) {
          _mlbamCache[p.name] = String(ppl[0].id);
          proceed(_mlbamCache[p.name]);
        } else {
          next();
        }
      })
      .catch(function () { next(); });
  }
}

function detectNewsItems(splits, player) {
  var items = [], isp = player.isp, added = 0;
  var recent = isp ? splits.slice(-5) : splits.slice(-7);
  if (!recent.length) return items;

  if (isp) {
    for (var i = recent.length - 1; i >= 0 && added < 2; i--) {
      var sp  = recent[i], s = sp.stat || {};
      var fp  = calcPitFP(s);
      var ip  = parseFloat(s.inningsPitched || '0');
      var er  = s.earnedRuns || 0, k = s.strikeOuts || 0;
      var sv  = s.saves || 0, hd = s.holds || 0;
      var dt  = (sp.date || '').slice(5);
      var opp = (sp.opponent && (sp.opponent.abbreviation || sp.opponent.name)) || '?';
      if (opp.length > 3) opp = opp.slice(0, 3);
      var fps  = (fp > 0 ? '+' : '') + fp.toFixed(1);
      var fpcls = fp >= 10 ? 'good' : fp <= -5 ? 'bad' : 'warn';
      var type = 'neutral', hl = '';
      if      (fp >= 18)        { type = 'good';    hl = 'Dominant start: ' + ip + ' IP, ' + k + ' K, ' + er + ' ER'; }
      else if (sv > 0)          { type = 'good';    hl = 'Save recorded (' + ip + ' IP)'; }
      else if (hd > 0)          { type = 'neutral'; hl = 'Hold recorded (' + ip + ' IP, ' + k + ' K)'; }
      else if (fp <= -8)        { type = 'bad';     hl = 'Rough outing: ' + er + ' ER in ' + ip + ' IP'; }
      else if (ip >= 6 && er <= 3) { type = 'good'; hl = 'Quality Start: ' + ip + ' IP, ' + k + ' K'; }
      else continue;
      items.push({ type:type, headline:hl, detail:opp+' \u00b7 '+dt, fp:fps, fpcls:fpcls, player:player, date:sp.date||'' });
      added++;
    }
  } else {
    // Hitting streak
    var streak = 0;
    for (var j = recent.length - 1; j >= 0; j--) {
      var s2 = recent[j].stat || {};
      if ((s2.hits || 0) > 0)           { streak++; }
      else if ((s2.atBats || 0) >= 3)   { break; }
    }
    if (streak >= 3 && added < 2) {
      items.push({ type:'good', headline:streak+'-game hitting streak',
        detail:'Last '+recent.length+' games', fp:'', fpcls:'good', player:player, date:(recent[recent.length-1].date||'') });
      added++;
    }
    // Slump
    var slump = 0;
    for (var jj = recent.length - 1; jj >= 0; jj--) {
      var s3 = recent[jj].stat || {};
      if ((s3.atBats || 0) >= 3 && (s3.hits || 0) === 0) { slump++; }
      else if ((s3.atBats || 0) >= 3)                     { break; }
    }
    if (slump >= 3 && added < 2) {
      items.push({ type:'bad', headline:'0-for-last-'+slump+' slump (AB \u2265 3)',
        detail:'Last '+recent.length+' games', fp:'', fpcls:'bad', player:player, date:(recent[recent.length-1].date||'') });
      added++;
    }
    // Big games
    for (var k2 = recent.length - 1; k2 >= 0 && added < 2; k2--) {
      var sp3  = recent[k2], s4 = sp3.stat || {};
      var fp3  = calcBatFP(s4);
      var hr3  = s4.homeRuns || 0, h3 = s4.hits || 0, ab3 = s4.atBats || 0;
      var fps3 = (fp3 > 0 ? '+' : '') + fp3.toFixed(1);
      var fpcls3 = fp3 >= 10 ? 'good' : fp3 < 0 ? 'bad' : 'warn';
      var dt3  = (sp3.date || '').slice(5);
      var opp3 = (sp3.opponent && (sp3.opponent.abbreviation || sp3.opponent.name)) || '?';
      if (opp3.length > 3) opp3 = opp3.slice(0, 3);
      var type3 = 'neutral', hl3 = '';
      if      (hr3 >= 2)   { type3 = 'good'; hl3 = hr3+'-HR game: '+h3+'-for-'+ab3+', '+(s4.rbi||0)+' RBI'; }
      else if (fp3 >= 15)  { type3 = 'good'; hl3 = 'Huge game: '+h3+'-for-'+ab3+', '+hr3+' HR, '+(s4.rbi||0)+' RBI'; }
      else if (h3 >= 4)    { type3 = 'good'; hl3 = '4-hit game ('+h3+'-for-'+ab3+')'; }
      else continue;
      items.push({ type:type3, headline:hl3, detail:opp3+' \u00b7 '+dt3, fp:fps3, fpcls:fpcls3, player:player, date:sp3.date||'' });
      added++;
    }
  }
  return items;
}

function renderNews(items) {
  var wrap = document.getElementById('news-list-wrap');
  if (!wrap) return;
  if (!items.length) {
    wrap.innerHTML = '<div class="news-empty">Nothing notable in the last 7 days.</div>';
    return;
  }
  items.sort(function (a, b) { return b.date > a.date ? 1 : b.date < a.date ? -1 : 0; });
  var html = '';
  for (var i = 0; i < items.length; i++) {
    var it = items[i], p = it.player;
    var avHtml = '';
    if (p.hs) {
      avHtml  = '<img src="' + p.hs + '" alt="' + p.name + '" loading="lazy" ';
      if (p.hs2)
        avHtml += 'onerror="this.src=\'' + p.hs2 + '\';this.onerror=function(){this.style.display=\'none\';this.nextSibling.style.display=\'flex\';}" ';
      else
        avHtml += 'onerror="this.style.display=\'none\';this.nextSibling.style.display=\'flex\';" ';
      avHtml += '><span class="av-fb" style="display:none">' + p.ini + '</span>';
    } else {
      avHtml = '<span class="av-fb">' + p.ini + '</span>';
    }
    var fpHtml = it.fp ? '<div class="news-fp ' + it.fpcls + '">' + it.fp + '</div>' : '';
    html += '<div class="news-card news-' + it.type + '">'
          + '<div class="news-av">' + avHtml + '</div>'
          + '<div class="news-body">'
          + '<div class="news-name">'     + p.name       + '</div>'
          + '<div class="news-headline">' + it.headline  + '</div>'
          + '<div class="news-detail">'   + it.detail    + '</div>'
          + '</div>' + fpHtml + '</div>';
  }
  wrap.innerHTML = '<div class="news-list">' + html + '</div>';
}

function calcBatFP(s) {
  var tb = (s.hits || 0) + (s.doubles || 0) + (s.triples || 0) * 2 + (s.homeRuns || 0) * 3;
  return (s.runs || 0) * 1
       + (s.homeRuns || 0) * 1
       + tb * 1
       + (s.rbi || 0) * 1
       + (s.baseOnBalls || 0) * 1
       + (s.stolenBases || 0) * 1
       + (s.strikeOuts || 0) * -1;
}

function calcPitFP(s) {
  var ip  = parseFloat(s.inningsPitched || '0');
  var qs  = (ip >= 6 && (s.earnedRuns || 0) <= 3) ? 1 : 0;
  var sv  = s.saves || 0;
  var hd  = s.holds || 0;
  return ip * 3
       + (s.hits        || 0) * -1
       + (s.earnedRuns  || 0) * -2
       + (s.homeRuns    || 0) * -1
       + (s.baseOnBalls || 0) * -1
       + (s.strikeOuts  || 0) *  1
       + qs *  2
       + (s.wins        || 0) *  2
       + (s.losses      || 0) * -2
       + sv * 6
       + (s.blownSaves  || 0) * -3
       + hd * 5
       + (sv + hd) * 2;
}

function doFetchGameLog(mid, isp, year) {
  if (!year) year = FDB_YEAR;
  var grp = isp ? 'pitching' : 'hitting';
  var url = 'https://statsapi.mlb.com/api/v1/people/' + mid +
            '/stats?stats=gameLog&season=' + year + '&group=' + grp;
  fetch(url)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var sp = (data.stats && data.stats[0] && data.stats[0].splits) || [];
      renderGameLog(sp.slice(-10).reverse(), isp);
    })
    .catch(function () {
      var w = document.getElementById('pm-log-wrap');
      if (w) w.innerHTML = '<div class="pm-empty">Could not load game log.</div>';
    });
}

function fetchGameLog(mid, isp, pname, year) {
  if (!year) year = FDB_YEAR;
  if (mid) { doFetchGameLog(mid, isp, year); return; }
  if (_mlbamCache[pname]) { doFetchGameLog(_mlbamCache[pname], isp, year); return; }

  var surl = 'https://statsapi.mlb.com/api/v1/people/search?names=' +
             encodeURIComponent(pname) + '&sportId=1';
  fetch(surl)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var people = (data.people || []).filter(function (p) { return p.active !== false; });
      if (!people.length) people = data.people || [];
      if (people.length) {
        _mlbamCache[pname] = String(people[0].id);
        doFetchGameLog(_mlbamCache[pname], isp, year);
      } else {
        var w = document.getElementById('pm-log-wrap');
        if (w) w.innerHTML = '<div class="pm-empty">No MLB stats found for this player.</div>';
      }
    })
    .catch(function () {
      var w = document.getElementById('pm-log-wrap');
      if (w) w.innerHTML = '<div class="pm-empty">Could not load game log.</div>';
    });
}

function renderGameLog(splits, isp) {
  var w = document.getElementById('pm-log-wrap');
  if (!w) return;
  if (!splits.length) {
    w.innerHTML = '<div class="pm-empty">No games played yet this season.</div>';
    return;
  }

  var totFP = 0, rows = '';
  for (var i = 0; i < splits.length; i++) {
    var sp  = splits[i], s = sp.stat || {};
    var dt  = (sp.date || '').slice(5);
    var opp = (sp.opponent && (sp.opponent.abbreviation || sp.opponent.name)) || '?';
    if (opp.length > 3) opp = opp.slice(0, 3);
    var loc  = (sp.isHome === false) ? '@' : '';
    var fp   = isp ? calcPitFP(s) : calcBatFP(s);
    totFP   += fp;
    var fcls = fp >= 10 ? 'good' : fp <= 0 ? 'bad' : fp >= 5 ? '' : 'warn';
    var fps  = (fp > 0 ? '+' : '') + fp.toFixed(1);

    if (isp) {
      var ip   = parseFloat(s.inningsPitched || '0');
      var qs   = (ip >= 6 && (s.earnedRuns || 0) <= 3) ? 'Y' : '';
      var wl   = s.wins ? 'W' : s.losses ? 'L' : '';
      var era  = ip > 0 ? (((s.earnedRuns  || 0) / ip) * 9).toFixed(2) : '\u2014';
      var whip = ip > 0 ? (((s.hits || 0) + (s.baseOnBalls || 0)) / ip).toFixed(2) : '\u2014';
      rows += '<tr>'
            + '<td class="pm-sticky">' + dt + '</td>'
            + '<td>' + loc + opp + '</td>'
            + '<td>' + (s.inningsPitched || '0') + '</td>'
            + '<td>' + (s.hits           || 0) + '</td>'
            + '<td>' + (s.earnedRuns     || 0) + '</td>'
            + '<td>' + (s.baseOnBalls    || 0) + '</td>'
            + '<td>' + (s.strikeOuts     || 0) + '</td>'
            + '<td>' + (s.homeRuns       || 0) + '</td>'
            + '<td>' + wl  + '</td>'
            + '<td>' + (s.saves          || 0) + '</td>'
            + '<td>' + (s.holds          || 0) + '</td>'
            + '<td>' + qs  + '</td>'
            + '<td>' + era + '</td>'
            + '<td>' + whip + '</td>'
            + '<td class="pm-fp ' + fcls + '">' + fps + '</td>'
            + '</tr>';
    } else {
      var ab  = s.atBats || 0, h = s.hits || 0;
      var tb  = h + (s.doubles || 0) + (s.triples || 0) * 2 + (s.homeRuns || 0) * 3;
      var avg = ab > 0 ? (h / ab).toFixed(3).replace('0.', '.') : '\u2014';
      var pa  = ab + (s.baseOnBalls || 0) + (s.hitByPitch || 0) + (s.sacFlies || 0);
      var obp = pa > 0
        ? ((h + (s.baseOnBalls || 0) + (s.hitByPitch || 0)) / pa).toFixed(3).replace('0.', '.')
        : '\u2014';
      rows += '<tr>'
            + '<td class="pm-sticky">' + dt + '</td>'
            + '<td>' + loc + opp + '</td>'
            + '<td>' + ab + '</td>'
            + '<td>' + h  + '</td>'
            + '<td>' + (s.doubles   || 0) + '</td>'
            + '<td>' + (s.triples   || 0) + '</td>'
            + '<td>' + (s.homeRuns  || 0) + '</td>'
            + '<td>' + (s.runs      || 0) + '</td>'
            + '<td>' + (s.rbi       || 0) + '</td>'
            + '<td>' + (s.baseOnBalls || 0) + '</td>'
            + '<td>' + (s.strikeOuts  || 0) + '</td>'
            + '<td>' + (s.stolenBases || 0) + '</td>'
            + '<td>' + avg + '</td>'
            + '<td>' + obp + '</td>'
            + '<td class="pm-fp ' + fcls + '">' + fps + '</td>'
            + '</tr>';
    }
  }

  var avgFP   = splits.length ? (totFP / splits.length).toFixed(1) : '0.0';
  var summary = '<div class="pm-fp-summary">Avg FP / game (last ' + splits.length + '): '
              + '<b style="color:var(--accent)">' + avgFP + '</b></div>';
  var hdr = isp
    ? '<tr><th class="pm-sticky">Date</th><th>Opp</th><th>IP</th><th>H</th>'
      + '<th>ER</th><th>BB</th><th>K</th><th>HR</th><th>W/L</th>'
      + '<th>SV</th><th>HD</th><th>QS</th><th>ERA</th><th>WHIP</th>'
      + '<th class="pm-fp-hdr">FP</th></tr>'
    : '<tr><th class="pm-sticky">Date</th><th>Opp</th><th>AB</th><th>H</th>'
      + '<th>2B</th><th>3B</th><th>HR</th><th>R</th><th>RBI</th>'
      + '<th>BB</th><th>K</th><th>SB</th><th>AVG</th><th>OBP</th>'
      + '<th class="pm-fp-hdr">FP</th></tr>';

  w.innerHTML = summary
              + '<table class="pm-log-table"><thead>' + hdr + '</thead>'
              + '<tbody>' + rows + '</tbody></table>';
}

// ── Extended module code (player modal, comparisons, analytics, trade) ────────

// ── Inner sub-tab switcher (Matchup: Overview | Compare) ─────────────────────
function switchInnerTab(tab){
  document.querySelectorAll('.inner-pane').forEach(function(p){
    p.classList.toggle('visible', p.id==='ipane-'+tab);
  });
  document.querySelectorAll('.inner-tab-btn').forEach(function(b){
    b.classList.toggle('active', b.id==='itb-'+tab);
  });
}

function switchTodayTab(tab){
  document.querySelectorAll('.today-pane').forEach(function(p){
    p.classList.toggle('visible', p.id==='tdpane-'+tab);
  });
  var pane = document.querySelector('.tab-pane[data-tab="today"]');
  if(pane) pane.querySelectorAll('.inner-tab-btn').forEach(function(b){
    b.classList.toggle('active', b.id==='tdtb-'+tab);
  });
}

function switchToolsTab(tab){
  document.querySelectorAll('.tools-pane').forEach(function(p){
    p.classList.toggle('visible', p.id==='tspane-'+tab);
  });
  var pane = document.querySelector('.tab-pane[data-tab="tools"]');
  if(pane) pane.querySelectorAll('.inner-tab-btn').forEach(function(b){
    b.classList.toggle('active', b.id==='tstb-'+tab);
  });
  if(tab==='trade') setTimeout(tc_lazyBuild, 50);
}

function toggleMoreMenu(){
  var menu = document.getElementById('tab-more-menu');
  if(menu) menu.classList.toggle('open');
}

document.addEventListener('click', function(e){
  if(!e.target.closest || !e.target.closest('.tab-more-wrap')){
    var menu = document.getElementById('tab-more-menu');
    if(menu) menu.classList.remove('open');
  }
});

// ── Comparison engine ─────────────────────────────────────────────────────────
var _cmpSlot={mine:null,opp:null};
var _cmpStats={mine:null,opp:null};
var _cmpPending={mine:false,opp:false};

function cmpDragStart(e,el){
  var raw=el.getAttribute('data-player');
  e.dataTransfer.setData('text/plain',raw);
  e.dataTransfer.effectAllowed='copy';
  el.classList.add('dragging');
  setTimeout(function(){el.classList.remove('dragging');},80);
}

function cmpDragOver(e){
  e.preventDefault();
  e.dataTransfer.dropEffect='copy';
  e.currentTarget.classList.add('dragover');
}

function cmpDragLeave(e){
  e.currentTarget.classList.remove('dragover');
}

function cmpDrop(e,slot){
  e.preventDefault();
  e.currentTarget.classList.remove('dragover');
  var raw=e.dataTransfer.getData('text/plain');
  if(!raw)return;
  try{
    var p=JSON.parse(raw);
    _cmpSlot[slot]=p;
    _cmpStats[slot]=null;
    _cmpPending[slot]=true;
    _renderDropZone(slot,p);
    _renderCmpTable();      // show scaffold with "loading stats..."
    _fetchSeasonStats(p.mlbam,p.isp,slot);
  }catch(ex){console.warn('cmpDrop parse error',ex);}
}

function clearSlot(slot){
  _cmpSlot[slot]=null;
  _cmpStats[slot]=null;
  _cmpPending[slot]=false;
  var dz=document.getElementById('dz-'+slot);
  if(dz){
    dz.classList.remove('filled');
    dz.innerHTML='<div class="drop-zone-hint">'+(slot==='mine'?'↓ Drop your player here':'↓ Drop opponent player here')+'</div>';
  }
  document.getElementById('cmp-result').innerHTML='';
}

function _renderDropZone(slot,p){
  var dz=document.getElementById('dz-'+slot);
  if(!dz)return;
  dz.classList.add('filled');
  var avHtml='';
  if(p.hs){
    avHtml='<img src="'+p.hs+'" alt="'+p.name+'" '+(p.hs2?'onerror="this.src=\''+p.hs2+'\';this.onerror=function(){this.style.display=\'none\';this.nextSibling.style.display=\'flex\';};"':'onerror="this.style.display=\'none\';this.nextSibling.style.display=\'flex\';"')+'>';
    avHtml+='<div class="dz-av-fb" style="display:none">'+p.ini+'</div>';
  }else{
    avHtml='<div class="dz-av-fb">'+p.ini+'</div>';
  }
  var posS=(p.pos||'').replace(/[^A-Z0-9]/g,'');
  dz.innerHTML=(
    '<div class="dz-player">'+
    '<div class="dz-av">'+avHtml+'</div>'+
    '<div class="dz-info">'+
    '<div class="dz-name">'+p.name+'</div>'+
    '<div class="dz-sub"><span class="pos pos-'+posS+'">'+p.pos+'</span><span>'+p.mlb+'</span></div>'+
    '</div>'+
    '<button class="dz-clear" onclick="clearSlot(\''+slot+'\')">&#x2715;</button>'+
    '</div>'
  );
}

function _fetchSeasonStats(mlbam,isp,slot){
  if(!mlbam){_cmpStats[slot]={};_cmpPending[slot]=false;_renderCmpTable();return;}
  var grp=isp?'pitching':'hitting';
  var url='https://statsapi.mlb.com/api/v1/people/'+mlbam+'/stats?stats=season&season='+FDB_YEAR+'&group='+grp;
  fetch(url,{signal:AbortSignal.timeout(8000)}).then(function(r){return r.json();}).then(function(data){
    var sp=data.stats&&data.stats[0]&&data.stats[0].splits||[];
    _cmpStats[slot]=(sp.length&&sp[0].stat)?sp[0].stat:{};
    _cmpPending[slot]=false;
    _renderCmpTable();
  }).catch(function(){
    _cmpStats[slot]={};_cmpPending[slot]=false;_renderCmpTable();
  });
}

// _cmpRow: metric label, numeric values for comparison, optional display overrides
function _cmpRow(metric,aNum,bNum,lowerBetter,aDisp,bDisp){
  var aV=parseFloat(aNum),bV=parseFloat(bNum);
  var aWin=false,bWin=false;
  if(!isNaN(aV)&&!isNaN(bV)&&aNum!=='—'&&bNum!=='—'){
    aWin=lowerBetter?(aV<bV):(aV>bV);
    bWin=lowerBetter?(bV<aV):(bV>aV);
  }
  var aD=(aDisp!==undefined)?aDisp:(aNum==='—'?'—':aNum);
  var bD=(bDisp!==undefined)?bDisp:(bNum==='—'?'—':bNum);
  return('<tr>'+
    '<td>'+metric+'</td>'+
    '<td class="'+(aWin?'cmp-win':bWin?'cmp-lose':'')+'">'+aD+'</td>'+
    '<td class="'+(bWin?'cmp-win':aWin?'cmp-lose':'')+'">'+bD+'</td>'+
    '</tr>');
}

function _sectionRow(label){
  return '<tr><td class="cmp-section" colspan="3">'+label+'</td></tr>';
}

function _renderCmpTable(){
  var a=_cmpSlot.mine,b=_cmpSlot.opp;
  var el=document.getElementById('cmp-result');
  if(!el)return;
  if(!a||!b){el.innerHTML='';return;}

  var sa=_cmpStats.mine,sb=_cmpStats.opp;
  var loading=_cmpPending.mine||_cmpPending.opp;
  var rows='';

  // ── Model scores ────────────────────────────────────────────────────────────
  rows+=_sectionRow('Model Scores');
  rows+=_cmpRow('Val (0–100)',a.base,b.base,false);
  rows+=_cmpRow('Fit (0–100)',a.fit,b.fit,false);
  rows+=_cmpRow('Proj Pts',a.proj,b.proj,false);
  rows+=_cmpRow('Above Repl',a.var,b.var,false);
  rows+=_cmpRow('Repl Pts',a.repl,b.repl,true);

  // Tier (string compare — map to ordinal)
  var tO={Elite:5,Starter:4,Depth:3,Replacement:2,Droppable:1};
  rows+=_cmpRow('Tier',tO[a.tier]||0,tO[b.tier]||0,false,a.tier||'—',b.tier||'—');

  // Status
  var aS=(!a.status||a.status==='ACTIVE'||a.status==='NORMAL')?'✓ Active':'⚠ '+a.status;
  var bS=(!b.status||b.status==='ACTIVE'||b.status==='NORMAL')?'✓ Active':'⚠ '+b.status;
  rows+='<tr><td>Status</td><td>'+aS+'</td><td>'+bS+'</td></tr>';

  // Weekly starts (pitchers)
  if(a.isp||b.isp){
    var awN=a.ws>=0?a.ws:(a.isp?0:-999);
    var bwN=b.ws>=0?b.ws:(b.isp?0:-999);
    var awD=a.ws>=0?a.ws+(a.ws===1?' start':' starts'):(a.isp?'?':'—');
    var bwD=b.ws>=0?b.ws+(b.ws===1?' start':' starts'):(b.isp?'?':'—');
    rows+=_cmpRow('This Week',awN,bwN,false,awD,bwD);
  }

  // ── Season stats ─────────────────────────────────────────────────────────────
  rows+=_sectionRow('Season Stats ('+(loading?'loading…':FDB_YEAR)+')');

  if(loading){
    rows+='<tr><td colspan="3" style="text-align:center;color:var(--text2);padding:12px">Fetching stats…</td></tr>';
  } else {
    var g=function(obj,k){return(obj&&obj[k]!==undefined&&obj[k]!==null)?obj[k]:null;};
    var f1=function(v){return v!==null?parseFloat(v).toFixed(1):'—';};
    var f2=function(v){return v!==null?parseFloat(v).toFixed(2):'—';};
    var f3=function(v){return v!==null?parseFloat(v).toFixed(3):'—';};
    var fi=function(v){return v!==null?parseInt(v,10):'—';};

    var bothP=a.isp&&b.isp,bothH=!a.isp&&!b.isp;

    if(bothP){
      var aIP=g(sa,'inningsPitched'),bIP=g(sb,'inningsPitched');
      rows+=_cmpRow('IP',aIP!==null?parseFloat(aIP):NaN,bIP!==null?parseFloat(bIP):NaN,false,f1(aIP),f1(bIP));
      rows+=_cmpRow('ERA',g(sa,'era'),g(sb,'era'),true,f2(g(sa,'era')),f2(g(sb,'era')));
      rows+=_cmpRow('WHIP',g(sa,'whip'),g(sb,'whip'),true,f2(g(sa,'whip')),f2(g(sb,'whip')));
      rows+=_cmpRow('K',g(sa,'strikeOuts'),g(sb,'strikeOuts'),false,fi(g(sa,'strikeOuts')),fi(g(sb,'strikeOuts')));
      rows+=_cmpRow('BB',g(sa,'baseOnBalls'),g(sb,'baseOnBalls'),true,fi(g(sa,'baseOnBalls')),fi(g(sb,'baseOnBalls')));
      rows+=_cmpRow('W',g(sa,'wins'),g(sb,'wins'),false,fi(g(sa,'wins')),fi(g(sb,'wins')));
      rows+=_cmpRow('SV',g(sa,'saves'),g(sb,'saves'),false,fi(g(sa,'saves')),fi(g(sb,'saves')));
      rows+=_cmpRow('HD',g(sa,'holds'),g(sb,'holds'),false,fi(g(sa,'holds')),fi(g(sb,'holds')));
      rows+=_cmpRow('QS',g(sa,'qualityStarts'),g(sb,'qualityStarts'),false,fi(g(sa,'qualityStarts')),fi(g(sb,'qualityStarts')));
    } else if(bothH){
      rows+=_cmpRow('HR',g(sa,'homeRuns'),g(sb,'homeRuns'),false,fi(g(sa,'homeRuns')),fi(g(sb,'homeRuns')));
      rows+=_cmpRow('RBI',g(sa,'rbi'),g(sb,'rbi'),false,fi(g(sa,'rbi')),fi(g(sb,'rbi')));
      rows+=_cmpRow('R',g(sa,'runs'),g(sb,'runs'),false,fi(g(sa,'runs')),fi(g(sb,'runs')));
      rows+=_cmpRow('SB',g(sa,'stolenBases'),g(sb,'stolenBases'),false,fi(g(sa,'stolenBases')),fi(g(sb,'stolenBases')));
      rows+=_cmpRow('BB',g(sa,'baseOnBalls'),g(sb,'baseOnBalls'),false,fi(g(sa,'baseOnBalls')),fi(g(sb,'baseOnBalls')));
      rows+=_cmpRow('K',g(sa,'strikeOuts'),g(sb,'strikeOuts'),true,fi(g(sa,'strikeOuts')),fi(g(sb,'strikeOuts')));
      rows+=_cmpRow('AVG',g(sa,'avg'),g(sb,'avg'),false,f3(g(sa,'avg')),f3(g(sb,'avg')));
      rows+=_cmpRow('OBP',g(sa,'obp'),g(sb,'obp'),false,f3(g(sa,'obp')),f3(g(sb,'obp')));
      rows+=_cmpRow('SLG',g(sa,'slg'),g(sb,'slg'),false,f3(g(sa,'slg')),f3(g(sb,'slg')));
      rows+=_cmpRow('OPS',g(sa,'ops'),g(sb,'ops'),false,f3(g(sa,'ops')),f3(g(sb,'ops')));
    } else {
      rows+='<tr><td colspan="3" style="text-align:center;color:var(--text2);font-size:11px;padding:10px">Mixed pitcher / hitter — raw stats not directly comparable</td></tr>';
    }
  }

  var aLast=a.name.split(' ').slice(-1)[0];
  var bLast=b.name.split(' ').slice(-1)[0];
  el.innerHTML=(
    '<div class="cmp-tbl-wrap">'+
    '<table class="cmp-tbl">'+
    '<thead><tr>'+
    '<th>Metric</th>'+
    '<th title="'+a.name+'">'+aLast+'</th>'+
    '<th title="'+b.name+'">'+bLast+'</th>'+
    '</tr></thead>'+
    '<tbody>'+rows+'</tbody>'+
    '</table></div>'
  );
}

function cmpFilter(side,val){
  var list=document.getElementById('cmp-list-'+side);
  if(!list)return;
  list.querySelectorAll('.drag-card').forEach(function(card){
    try{
      var d=JSON.parse(card.getAttribute('data-player'));
      var show=(val==='all')||(val==='P'&&d.isp)||(val==='H'&&!d.isp);
      card.style.display=show?'flex':'none';
    }catch(ex){}
  });
}


// ── My Team tab — arrow cycle navigation through all league teams ─────────────
(function () {
  var _tvIdx = 0;   // tracks currently visible pane index

  function _panes() {
    return Array.from(document.querySelectorAll('.team-viewer-pane'));
  }

  /** Update nav header label AND flip the top tab button text */
  function _applyPane(pane) {
    var dispName = pane ? (pane.dataset.displayName || pane.dataset.team || '') : '';
    // In-pane header
    var nameEl = document.getElementById('tv-team-name');
    if (nameEl) nameEl.textContent = dispName;
    // Top nav tab button: "My Team" when own team is shown, "Teams" otherwise
    var tabBtn = document.getElementById('tab-btn-myteam');
    if (tabBtn) tabBtn.textContent = (dispName === 'My Team') ? 'My Team' : 'Teams';
  }

  /** Cycle left (dir=-1) or right (dir=+1) through teams */
  window.teamViewStep = function (dir) {
    var panes = _panes();
    if (!panes.length) return;
    panes[_tvIdx].style.display = 'none';
    _tvIdx = (_tvIdx + dir + panes.length) % panes.length;
    panes[_tvIdx].style.display = 'block';
    _applyPane(panes[_tvIdx]);
    // Scroll the arrow nav bar back into view when paging through teams
    var nav = document.querySelector('.tv-nav');
    if (nav) nav.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  /** Jump directly to a team by raw name (legacy helper) */
  window.switchTeamView = function (name) {
    var panes = _panes();
    panes.forEach(function (p, i) {
      var match = p.dataset.team === name;
      p.style.display = match ? 'block' : 'none';
      if (match) { _tvIdx = i; _applyPane(p); }
    });
  };
}());

// ── Injury banner — return date & days out fetched from MLB Stats API ─────────
var _INJ_LABELS = {
  'DAY_TO_DAY':       'Day-to-Day',
  'QUESTIONABLE':     'Questionable',
  'DOUBTFUL':         'Doubtful',
  'OUT':              'Out',
  'FIFTEEN_DAY_DL':  '15-Day IL',
  'SIXTY_DAY_DL':    '60-Day IL',
  'INJURED_RESERVE': 'IL',
  'IR':               'IL',
  'SUSPENSION':      'Suspended',
  'NA':               'N/A',
};

/** Returns a human string like "12 days", "3 mo", "1.8 yrs" for elapsed days since injDate. */
function _fmtTimeOut(injDate) {
  if (!injDate) return null;
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var d     = new Date(injDate + 'T00:00:00');
  var days  = Math.round((today - d) / 86400000);
  if (days <= 0) return null;
  if (days < 30)  return days + ' day' + (days === 1 ? '' : 's');
  if (days < 365) return Math.round(days / 30) + ' mo';
  return (days / 365).toFixed(1) + ' yrs';
}

/** Returns "Mon DD, YYYY" for a date string. */
function _fmtDate(ds) {
  if (!ds) return null;
  try {
    return new Date(ds + 'T00:00:00').toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric'
    });
  } catch (e) { return ds; }
}

/** Days from today until retDate (positive = future, negative = overdue). */
function _daysUntil(retDate) {
  if (!retDate) return null;
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var d = new Date(retDate + 'T00:00:00');
  return Math.round((d - today) / 86400000);
}

function _renderInjBanner(injStatus, desc, injDate, retDate) {
  var banner = document.getElementById('pm-inj-banner');
  if (!banner) return;

  var label    = _INJ_LABELS[injStatus] || (injStatus ? injStatus.replace(/_/g, ' ') : 'Injured');
  var timeOut  = _fmtTimeOut(injDate);
  var retFmt   = _fmtDate(retDate);
  var daysLeft = _daysUntil(retDate);

  // Left: status pill + description
  var leftHtml = '<span class="pm-inj-pill">🏥 ' + label + '</span>'
               + (desc ? '<span class="pm-inj-desc">' + desc + '</span>' : '');

  // Right: two stat boxes (time out, return date)
  var rightHtml = '';
  if (timeOut) {
    rightHtml += '<div class="pm-inj-stat">'
               + '<span class="pm-inj-num">' + timeOut + '</span>'
               + '<span class="pm-inj-lbl">time out</span>'
               + '</div>';
  }
  if (retFmt) {
    var soon = (daysLeft !== null && daysLeft >= 0 && daysLeft <= 21) ? ' pm-inj-soon' : '';
    var sub  = (daysLeft !== null && daysLeft >= 0)
               ? ' <span class="pm-inj-sub">in ' + daysLeft + 'd</span>'
               : (daysLeft !== null && daysLeft < 0 ? ' <span class="pm-inj-sub">overdue</span>' : '');
    rightHtml += '<div class="pm-inj-stat' + soon + '">'
               + '<span class="pm-inj-num">' + retFmt + sub + '</span>'
               + '<span class="pm-inj-lbl">est. return</span>'
               + '</div>';
  } else {
    rightHtml += '<div class="pm-inj-stat">'
               + '<span class="pm-inj-num">TBD</span>'
               + '<span class="pm-inj-lbl">return date</span>'
               + '</div>';
  }

  banner.innerHTML = '<div class="pm-inj-left">' + leftHtml + '</div>'
                   + '<div class="pm-inj-right">' + rightHtml + '</div>';
}

function fetchInjuryBanner(mlbam, injStatus, pname) {
  function doFetch(mid) {
    if (!mid) { _renderInjBanner(injStatus, '', null, null); return; }
    fetch('https://statsapi.mlb.com/api/v1/people/' + mid + '?hydrate=currentInjury')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var p   = (data.people || [])[0] || {};
        var inj = p.currentInjury || {};
        // MLB API uses camelCase; fall back to empty strings
        var desc    = inj.description || inj.type || '';
        var injDate = inj.date || null;
        var retDate = inj.expectedReturn || null;
        _renderInjBanner(injStatus, desc, injDate, retDate);
      })
      .catch(function () { _renderInjBanner(injStatus, '', null, null); });
  }

  if (mlbam) {
    _mlbamCache[pname] = _mlbamCache[pname] || mlbam;
    doFetch(mlbam);
  } else if (_mlbamCache[pname]) {
    doFetch(_mlbamCache[pname]);
  } else {
    // MLBAM ID not in ESPN data — search by name
    fetch('https://statsapi.mlb.com/api/v1/people/search?names='
          + encodeURIComponent(pname) + '&sportId=1')
      .then(function (r) { return r.json(); })
      .then(function (sd) {
        var ppl = (sd.people || []).filter(function (x) { return x.active !== false; });
        if (!ppl.length) ppl = sd.people || [];
        if (ppl.length) {
          _mlbamCache[pname] = String(ppl[0].id);
          doFetch(_mlbamCache[pname]);
        } else {
          _renderInjBanner(injStatus, '', null, null);
        }
      })
      .catch(function () { _renderInjBanner(injStatus, '', null, null); });
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// ── Advanced Stats — player modal enhancement ─────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

var _pmAdv = {};

// ══════════════════════════════════════════════════════════════════════════════
// COMPLETE MODAL OVERRIDE — replaces the minified openPlayerModal with a clean,
// tab-aware version that builds the full modal (header + Game Log + Advanced
// Stats tabs) in a single innerHTML assignment, eliminating fragile DOM injection.
// ══════════════════════════════════════════════════════════════════════════════
function openPlayerModal(ev, el) {
  if (ev && ev.stopPropagation) ev.stopPropagation();

  // Walk up DOM to find the element with data-name
  var t = el;
  while (t && !t.dataset.name) { t = t.parentElement; }
  if (!t || !t.dataset.name) return;

  var d     = t.dataset;
  var name  = d.name  || '';
  var team  = d.team  || '';
  var pos   = d.pos   || '';
  var base  = d.base  || '—';
  var fit   = d.fit   || '—';
  var proj  = d.proj  || '—';
  var hs    = d.hs    || '';
  var hs2   = d.hs2   || '';
  var ini   = d.ini   || (name.split(' ').map(function(w){return w[0]||'';}).join('')) || '?';
  var mlbam = d.mlbam || '';
  var isp   = d.pitcher === 'true';
  var onIl  = d.onIl  === 'true';
  var injStatus = d.injStatus || '';

  // Parse advanced stats JSON
  try { _pmAdv = d.adv ? JSON.parse(d.adv) : {}; } catch(e) { _pmAdv = {}; }
  if (!_pmAdv.fit  && d.fit)  _pmAdv.fit  = parseFloat(d.fit)  || 0;
  if (!_pmAdv.val  && d.base) _pmAdv.val  = parseFloat(d.base) || 0;
  if (!_pmAdv.bs   && d.base) _pmAdv.bs   = parseFloat(d.base) || 0;
  if (!_pmAdv.proj && d.proj) _pmAdv.proj = parseFloat(d.proj) || 0;

  // Store globals for async callbacks
  _pmName  = name;
  _pmIsp   = isp;
  _pmMlbam = mlbam;

  // ── Avatar HTML ──
  var avHtml;
  if (hs) {
    var onerr = hs2
      ? 'onerror="this.src=\'' + hs2 + '\';this.onerror=function(){this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';};"'
      : 'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';"';
    avHtml = '<img src="' + hs + '" alt="' + _esc(name) + '" loading="lazy" ' + onerr + '>'
           + '<span class="av-fb" style="display:none">' + _esc(ini) + '</span>';
  } else {
    avHtml = '<span class="av-fb">' + _esc(ini) + '</span>';
  }

  // ── Score badge colours ──
  var bv = parseFloat(base) || 0;
  var bc = bv >= 65 ? 'var(--accent)' : bv >= 38 ? 'var(--amber)' : 'var(--red)';
  var posS = pos.replace(/[^A-Z0-9]/g, '');

  // ── Injury banner ──
  var injBanner = onIl
    ? '<div id="pm-inj-banner" class="pm-inj-banner"><span class="pm-inj-loading">Loading injury details…</span></div>'
    : '';

  // ── Advanced stats pane content ──
  var advPaneContent = _buildAdvPaneHtml(_pmAdv, isp);

  // ── Year selector ──
  var yearOpts = buildYearOptions();

  // ── Full modal HTML — built in one shot ──
  var html =
    '<div class="pm-header">' +
      '<div class="pm-av">' + avHtml + '</div>' +
      '<div class="pm-info">' +
        '<div class="pm-name">' + _esc(name) + '</div>' +
        '<div class="pm-meta">' +
          '<span class="pos pos-' + posS + '">' + _esc(pos) + '</span>' +
          '<span style="color:var(--text2);font-size:13px">' + _esc(team) + '</span>' +
        '</div>' +
        '<div class="pm-scores">' +
          '<span class="pm-score-badge" style="border-color:' + bc + '">Val ' + _esc(base) + '</span>' +
          '<span class="pm-score-badge" style="border-color:#58a6ff">Fit ' + _esc(fit) + '</span>' +
          '<span class="pm-score-badge" style="border-color:var(--text2)">' + _esc(proj) + ' pts proj</span>' +
        '</div>' +
      '</div>' +
    '</div>' +
    injBanner +
    // Tab bar
    '<div class="pm-modal-tabs">' +
      '<button class="pm-modal-tab active" id="pm-tab-log" onclick="pmSwitchTab(\'log\')">▶︎ Game Log</button>' +
      '<button class="pm-modal-tab" id="pm-tab-adv" onclick="pmSwitchTab(\'adv\')">◕︎ Advanced Stats</button>' +
    '</div>' +
    // Game log pane
    '<div id="pm-pane-log">' +
      '<div class="pm-section-title" style="display:flex;align-items:center;justify-content:space-between;padding-right:20px">' +
        '<span>' + (isp ? 'Last 10 Outings' : 'Last 10 Games') + '</span>' +
        '<select id="pm-year-sel" class="pm-year-sel" onchange="changeModalYear(this.value)">' + yearOpts + '</select>' +
      '</div>' +
      '<div id="pm-log-wrap" class="pm-log-wrap"><div class="pm-loading">Loading game log…</div></div>' +
    '</div>' +
    // Advanced stats pane (hidden)
    '<div id="pm-pane-adv" class="adv-pane-hidden">' +
      advPaneContent +
    '</div>';

  var modal = document.getElementById('player-modal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  document.getElementById('pm-content').innerHTML = html;

  // Draw radar chart if applicable
  if (_pmAdv && (isp ? (_pmAdv.FIP || _pmAdv.SwStp || _pmAdv.K9) : (_pmAdv.wRCp || _pmAdv.wOBA))) {
    setTimeout(function(){ _drawRadar(_pmAdv, isp); }, 80);
  }

  // Kick off async fetches
  fetchGameLog(mlbam, isp, name, FDB_YEAR);
  if (onIl) fetchInjuryBanner(mlbam, injStatus, name);
};

// _pmEsc removed — use _esc() directly (same implementation, defined below as function declaration)

// Build the advanced stats pane content as an HTML string
function _buildAdvPaneHtml(adv, isp) {
  if (!adv || !Object.keys(adv).length) {
    return '<div class="adv-empty">No advanced stats available for this player.<br>' +
           '<small>Run <code>build_reference_cache.py --force</code> to populate.</small></div>';
  }
  var html = '<div class="adv-inner">';
  if (adv.signal) html += _signalHtml(adv.signal);
  html += _valueHtml(adv);

  // ── Two-column: dual-layer radar + actual-vs-expected verdict card ────────
  var hasRadar = isp ? (adv.FIP || adv.SwStp || adv.K9) : (adv.wRCp || adv.wOBA);
  var verdict  = _verdictCard(adv, isp);
  if (hasRadar || verdict) {
    html += '<div class="adv-main-row">';
    if (hasRadar) {
      html += '<div class="adv-radar-col">' +
              '<canvas id="adv-radar" width="210" height="210"></canvas>' +
              '<div class="adv-radar-legend">' +
                '<div class="adv-rl-item"><div class="adv-rl-dot" style="background:rgba(0,230,118,.55);border:2px solid #00e676"></div>Actual</div>' +
                '<div class="adv-rl-item"><div class="adv-rl-dot" style="background:rgba(88,166,255,.4);border:2px solid #58a6ff;border-style:dashed"></div>Expected</div>' +
              '</div></div>';
    }
    if (verdict) {
      html += '<div class="adv-verdict-col">' + verdict + '</div>';
    }
    html += '</div>';
  }

  // ── Percentile bars (full-width, sectioned) ───────────────────────────────
  html += isp ? _pitcherPctBars(adv) : _hitterPctBars(adv);

  html += '</div>';
  return html;
}

// Tab switcher for the player modal
function pmSwitchTab(tab) {
  var logPane = document.getElementById('pm-pane-log');
  var advPane = document.getElementById('pm-pane-adv');
  var tabLog  = document.getElementById('pm-tab-log');
  var tabAdv  = document.getElementById('pm-tab-adv');
  if (!logPane || !advPane) return;

  if (tab === 'log') {
    logPane.style.display = '';
    advPane.classList.add('adv-pane-hidden');
    if (tabLog) { tabLog.classList.add('active'); }
    if (tabAdv) { tabAdv.classList.remove('active'); }
  } else {
    logPane.style.display = 'none';
    advPane.classList.remove('adv-pane-hidden');
    if (tabLog) { tabLog.classList.remove('active'); }
    if (tabAdv) { tabAdv.classList.add('active'); }
    // Draw radar on first switch to adv tab (canvas needs to be visible)
    setTimeout(function(){ _drawRadar(_pmAdv, _pmIsp); }, 60);
  }
}

// ── Tab switcher (legacy alias routes through pmSwitchTab) ───────────────────
function _advTab(tab) {
  var logPane = document.getElementById('pm-pane-log');
  var advPane = document.getElementById('pm-pane-adv');
  if (!logPane || !advPane) return;
  logPane.style.display  = (tab === 'log') ? '' : 'none';
  advPane.className      = (tab === 'adv') ? ''  : 'adv-pane-hidden';
  document.querySelectorAll('.pm-modal-tab').forEach(function (b, i) {
    b.classList.toggle('active', (i === 0) === (tab === 'log'));
  });
}

// ── Format helpers ────────────────────────────────────────────────────────────
function _fv(v, dec, suffix) {
  if (v === undefined || v === null) return '—';
  var n = parseFloat(v);
  if (isNaN(n) || n === 0) return '—';
  return n.toFixed(dec !== undefined ? dec : 0) + (suffix || '');
}
function _fvp(v, dec) { return _fv(v, dec !== undefined ? dec : 1, '%'); }
function _gapHtml(gap) {
  if (!gap || Math.abs(gap) < 0.001) return '';
  var pos = gap > 0;
  return ' <span class="adv-gap-' + (pos ? 'pos' : 'neg') + '">' +
    (pos ? '▲' : '▼') + Math.abs(gap).toFixed(3) + '</span>';
}

// ── Signal banner ─────────────────────────────────────────────────────────────
var _SIG = {
  'BREAKOUT_CANDIDATE': { cls: 'adv-sig-buy',  icon: '🚀', label: 'Breakout Candidate',
    desc: 'xwOBA significantly outpaces actual wOBA — quality exceeds current results.' },
  'REGRESSION_RISK':    { cls: 'adv-sig-sell', icon: '⚠️', label: 'Regression Risk',
    desc: 'Actual wOBA running well ahead of xwOBA — performance likely to decline.' },
  'BUY_LOW':            { cls: 'adv-sig-buy',  icon: '💰', label: 'Buy Low',
    desc: 'ERA is inflated vs xERA — underlying quality suggests upcoming improvement.' },
  'SELL_HIGH':          { cls: 'adv-sig-sell', icon: '📈', label: 'Sell High',
    desc: 'ERA is outperforming xERA — regression is likely on the way.' },
  'NEUTRAL':            { cls: 'adv-sig-neutral', icon: '⚖️', label: 'Neutral',
    desc: 'Expected and actual stats are closely aligned.' },
};
function _signalHtml(sig) {
  var c = _SIG[sig] || _SIG['NEUTRAL'];
  return '<div class="adv-signal ' + c.cls + '">' +
    '<span class="adv-signal-icon">' + c.icon + '</span>' +
    '<div class="adv-signal-body">' +
    '<span class="adv-signal-label">' + c.label + '</span>' +
    '<span class="adv-signal-desc">' + c.desc + '</span>' +
    '</div></div>';
}

// ── Value breakdown strip ─────────────────────────────────────────────────────
function _valueHtml(adv) {
  var proj = parseFloat(adv.proj) || 0;
  var repl = parseFloat(adv.repl) || 0;
  var varV = parseFloat(adv.var)  || 0;
  var bs   = parseFloat(adv.val || adv.bs) || 0;
  var fit  = parseFloat(adv.fit)  || 0;
  if (!proj && !bs && !fit) return '';
  function bsCol(v) { return v >= 65 ? 'var(--accent)' : v >= 38 ? 'var(--amber)' : 'var(--red)'; }
  var items = [
    { label: 'Projected Pts',   val: proj.toFixed(1), color: '#58a6ff' },
    { label: 'Replacement Lvl', val: repl.toFixed(1), color: 'var(--text2)' },
    { label: 'Value Above Repl',val: (varV >= 0 ? '+' : '') + varV.toFixed(1), color: varV >= 0 ? 'var(--accent)' : 'var(--red)' },
    { label: 'Base Score',      val: bs.toFixed(1),   color: bsCol(bs) },
    { label: 'Fit Score',       val: fit.toFixed(1),  color: '#bc8cff' },
  ];
  var cells = items.map(function (it) {
    return '<div class="adv-val-cell">' +
      '<span class="adv-val-num" style="color:' + it.color + '">' + it.val + '</span>' +
      '<span class="adv-val-lbl">' + it.label + '</span>' +
      '</div>';
  }).join('<span class="adv-val-arrow">›</span>');
  return '<div class="adv-value-strip">' + cells + '</div>';
}

// ── Percentile approximation ──────────────────────────────────────────────────
// Piecewise-linear lookup: [rawVal, approxPercentile] pairs sorted low→high.
// For inverted metrics (lower = better) the pct still increases as the raw val
// moves toward the "better" end, so the table is authored accordingly.
var _PCT_MAPS = {
  // Hitters
  'wRC+': [[50,3],[80,15],[90,28],[100,50],[110,62],[120,72],[130,82],[145,90],[165,95],[190,98],[220,99]],
  'wOBA': [[.260,5],[.300,20],[.320,35],[.340,55],[.360,72],[.380,85],[.400,93],[.430,98]],
  'xwOBA':[[.260,5],[.300,20],[.320,35],[.340,55],[.360,72],[.380,85],[.400,93],[.430,98]],
  'ISO':  [[.070,5],[.110,20],[.140,35],[.165,50],[.190,65],[.220,80],[.250,90],[.280,96],[.310,99]],
  'BBp':  [[.03,5],[.05,18],[.07,40],[.09,60],[.11,75],[.13,86],[.15,92],[.18,97]],
  // K% is inverted: lower K% = better = higher pct
  'Kp':   [[.09,97],[.12,90],[.15,80],[.18,68],[.20,58],[.22,50],[.25,35],[.28,22],[.32,12],[.36,4]],
  'Brlp': [[.01,10],[.03,25],[.05,40],[.07,58],[.10,72],[.14,85],[.18,93],[.22,97],[.26,99]],
  'HHp':  [[.25,5],[.32,20],[.36,35],[.40,50],[.44,65],[.48,78],[.52,88],[.58,96]],
  'EV':   [[82,2],[85,12],[87,25],[88,38],[89,52],[90,65],[91,77],[92,87],[93,93],[94,97],[96,99]],
  'Spd':  [[23,3],[25,15],[26,30],[27,50],[28,70],[28.5,82],[29,90],[29.5,95],[30,99]],
  'BABIP':[[.240,10],[.270,25],[.290,40],[.300,50],[.315,65],[.330,78],[.345,88],[.360,95]],
  // Pitchers — ERA-type: lower raw = better = higher pct
  'ERA':  [[2.0,98],[2.5,93],[3.0,83],[3.5,70],[4.0,55],[4.5,38],[5.0,25],[5.5,15],[7.0,3]],
  'FIP':  [[2.0,98],[2.5,92],[3.0,82],[3.5,68],[4.0,52],[4.5,35],[5.0,20],[5.5,10],[6.5,3]],
  'xFIP': [[2.0,98],[2.5,92],[3.0,82],[3.5,68],[4.0,52],[4.5,35],[5.0,20],[5.5,10],[6.5,3]],
  'SIERA':[[2.0,99],[2.5,93],[3.0,82],[3.5,67],[4.0,50],[4.5,32],[5.0,17],[5.5,8],[6.0,3]],
  'xERA': [[2.0,99],[2.5,93],[3.0,82],[3.5,67],[4.0,50],[4.5,32],[5.0,17],[5.5,8],[6.0,3]],
  'WHIP': [[0.80,98],[0.90,93],[1.00,84],[1.10,72],[1.20,58],[1.35,40],[1.50,22],[1.70,10],[2.0,3]],
  'SwStp':[[.04,5],[.07,20],[.08,30],[.09,42],[.10,55],[.11,65],[.12,75],[.13,83],[.15,90],[.17,96],[.20,99]],
  'CSWp': [[.18,5],[.22,20],[.25,38],[.27,55],[.29,67],[.31,78],[.33,87],[.35,94],[.37,99]],
  'KBBp': [[-.05,5],[.00,15],[.05,28],[.08,38],[.10,48],[.13,58],[.16,68],[.19,78],[.22,86],[.26,93],[.30,98]],
  'K9':   [[4,5],[5,15],[6,28],[7,45],[8,60],[9,72],[10,83],[11,91],[12,96],[13,99]],
  // BB9 inverted: lower = better
  'BB9':  [[1.0,98],[1.5,92],[2.0,83],[2.5,70],[3.0,57],[3.5,42],[4.0,25],[5.0,10],[6.0,3]],
  'GBp':  [[.28,3],[.33,12],[.38,28],[.43,48],[.47,62],[.50,73],[.55,85],[.60,94],[.65,99]],
  // HRFBp inverted: lower = better
  'HRFBp':[[.04,94],[.06,84],[.08,73],[.10,60],[.12,50],[.15,35],[.20,18],[.25,8],[.30,2]],
  'LOBp': [[.55,3],[.62,12],[.66,28],[.70,45],[.73,58],[.75,68],[.78,78],[.80,87],[.85,96]],
};
function _approxPct(metric, rawVal) {
  var v   = parseFloat(rawVal) || 0;
  var pts = _PCT_MAPS[metric];
  if (!pts || !v) return 0;
  // Sort by rawVal ascending
  var lo = pts[0], hi = pts[pts.length - 1];
  if (v <= lo[0]) return lo[1];
  if (v >= hi[0]) return hi[1];
  for (var i = 0; i < pts.length - 1; i++) {
    var a = pts[i], b = pts[i + 1];
    if (v >= a[0] && v <= b[0]) {
      var t = (v - a[0]) / (b[0] - a[0]);
      return Math.round(a[1] + t * (b[1] - a[1]));
    }
  }
  return 50;
}
function _pctCls(p) {
  return p >= 80 ? 'pct-elite' : p >= 60 ? 'pct-great' : p >= 40 ? 'pct-avg' : p >= 25 ? 'pct-below' : 'pct-poor';
}
function _pctValClr(p) {
  return p >= 80 ? '#42a5f5' : p >= 60 ? '#66bb6a' : p >= 40 ? '#8b949e' : p >= 25 ? '#ffa726' : '#ef5350';
}
function _ordinal(n) {
  if (n >= 11 && n <= 13) return n + 'th';
  var r = n % 10;
  return n + (r === 1 ? 'st' : r === 2 ? 'nd' : r === 3 ? 'rd' : 'th');
}
function _pctRow(label, metric, rawVal, display) {
  var pct = _approxPct(metric, rawVal);
  if (!pct && !(parseFloat(rawVal))) return '';
  var cls = _pctCls(pct);
  var vc  = _pctValClr(pct);
  return '<div class="adv-pct-row">' +
    '<span class="adv-pct-label">' + label + '</span>' +
    '<div class="adv-pct-track"><div class="adv-pct-fill ' + cls + '" style="width:' + pct + '%"></div></div>' +
    '<span class="adv-pct-val" style="color:' + vc + '">' + display + '</span>' +
    '<span class="adv-pct-rank">' + _ordinal(pct) + '</span>' +
  '</div>';
}
function _pctSec(title) {
  return '<div class="adv-pct-sec">' + title + '</div>';
}

// ── Hitter percentile bars ────────────────────────────────────────────────────
function _hitterPctBars(adv) {
  var h = '';
  var wrc  = parseFloat(adv.wRCp)  || 0;
  var woba = parseFloat(adv.wOBA)  || 0;
  var iso  = parseFloat(adv.ISO)   || 0;
  if (wrc || woba || iso) {
    h += _pctSec('Production');
    if (wrc)  h += _pctRow('wRC+',  'wRC+',  wrc,  wrc.toFixed(0));
    if (woba) h += _pctRow('wOBA',  'wOBA',  woba, woba.toFixed(3));
    if (iso)  h += _pctRow('ISO',   'ISO',   iso,  iso.toFixed(3));
  }
  var bbp = parseFloat(adv.BBp) || 0;
  var kp  = parseFloat(adv.Kp)  || 0;
  var bab = parseFloat(adv.BABIP) || 0;
  if (bbp || kp) {
    h += _pctSec('Plate Discipline');
    if (bbp) h += _pctRow('BB%',   'BBp', bbp, (bbp * 100).toFixed(1) + '%');
    if (kp)  h += _pctRow('K% ↓', 'Kp',  kp,  (kp  * 100).toFixed(1) + '%');
    if (bab) h += _pctRow('BABIP', 'BABIP', bab, bab.toFixed(3));
  }
  var xw  = parseFloat(adv.xwOBA)    || 0;
  var brl = parseFloat(adv.Brlp)     || 0;
  var hh  = parseFloat(adv.HHp)      || 0;
  var ev  = parseFloat(adv.EV)       || 0;
  var spd = parseFloat(adv.SprintSpd || adv.Spd) || 0;
  if (xw || brl || hh || ev || spd) {
    h += _pctSec('Statcast');
    if (xw)  h += _pctRow('xwOBA',      'xwOBA', xw,  xw.toFixed(3));
    if (brl) h += _pctRow('Barrel%',    'Brlp',  brl, (brl * 100).toFixed(1) + '%');
    if (hh)  h += _pctRow('Hard Hit%',  'HHp',   hh,  (hh  * 100).toFixed(1) + '%');
    if (ev)  h += _pctRow('Exit Velo',  'EV',    ev,  ev.toFixed(1) + ' mph');
    if (spd) h += _pctRow('Sprint Spd', 'Spd',   spd, spd.toFixed(1) + ' ft/s');
  }
  return h;
}

// ── Pitcher percentile bars ───────────────────────────────────────────────────
function _pitcherPctBars(adv) {
  var h = '';
  var era  = parseFloat(adv.ERA)   || 0;
  var fip  = parseFloat(adv.FIP)   || 0;
  var xfip = parseFloat(adv.xFIP)  || 0;
  var si   = parseFloat(adv.SIERA) || 0;
  var xera = parseFloat(adv.xERA)  || 0;
  var whip = parseFloat(adv.WHIP)  || 0;
  if (era || fip || xfip || si || xera) {
    h += _pctSec('ERA Estimators  (↓ lower is better)');
    if (era)  h += _pctRow('ERA ↓',   'ERA',   era,  era.toFixed(2));
    if (fip)  h += _pctRow('FIP ↓',   'FIP',   fip,  fip.toFixed(2));
    if (xfip) h += _pctRow('xFIP ↓',  'xFIP',  xfip, xfip.toFixed(2));
    if (si)   h += _pctRow('SIERA ↓', 'SIERA', si,   si.toFixed(2));
    if (xera) h += _pctRow('xERA ↓',  'xERA',  xera, xera.toFixed(2));
    if (whip) h += _pctRow('WHIP ↓',  'WHIP',  whip, whip.toFixed(2));
  }
  var sw  = parseFloat(adv.SwStp) || 0;
  var csw = parseFloat(adv.CSWp)  || 0;
  var kbb = parseFloat(adv.KBBp)  || 0;
  var k9  = parseFloat(adv.K9)    || 0;
  var bb9 = parseFloat(adv.BB9)   || 0;
  if (sw || csw || kbb || k9 || bb9) {
    h += _pctSec('Stuff & Command');
    if (sw)  h += _pctRow('SwStr%',  'SwStp', sw,  (sw  * 100).toFixed(1) + '%');
    if (csw) h += _pctRow('CSW%',    'CSWp',  csw, (csw * 100).toFixed(1) + '%');
    if (kbb) h += _pctRow('K-BB%',   'KBBp',  kbb, (kbb * 100).toFixed(1) + '%');
    if (k9)  h += _pctRow('K/9',     'K9',    k9,  k9.toFixed(1));
    if (bb9) h += _pctRow('BB/9 ↓',  'BB9',   bb9, bb9.toFixed(1));
  }
  var gb   = parseFloat(adv.GBp)   || 0;
  var hrfb = parseFloat(adv.HRFBp) || 0;
  var lob  = parseFloat(adv.LOBp)  || 0;
  if (gb || hrfb || lob) {
    h += _pctSec('Batted Ball & Luck');
    if (gb)   h += _pctRow('GB%',     'GBp',   gb,   (gb   * 100).toFixed(1) + '%');
    if (hrfb) h += _pctRow('HR/FB ↓', 'HRFBp', hrfb, (hrfb * 100).toFixed(1) + '%');
    if (lob)  h += _pctRow('LOB%',    'LOBp',  lob,  (lob  * 100).toFixed(1) + '%');
  }
  return h;
}

// ── Actual vs Expected verdict card ──────────────────────────────────────────
function _verdictCard(adv, isp) {
  if (isp) {
    // Pitcher: ERA vs xERA (falls back to FIP if no xERA)
    var era  = parseFloat(adv.ERA)  || 0;
    var xera = parseFloat(adv.xERA) || parseFloat(adv.FIP) || 0;
    if (!era || !xera) return '';
    var xLbl   = adv.xERA ? 'xERA' : 'FIP';
    var gap    = era - xera;          // positive = ERA inflated = buy low
    var isBuy  = gap >=  0.75;
    var isSell = gap <= -0.75;
    var cardCls = isBuy ? 'vd-buy' : isSell ? 'vd-sell' : '';
    var gapCls  = isBuy ? 'gap-buy' : isSell ? 'gap-sell' : 'gap-neut';
    var arrow   = isBuy ? '▲' : isSell ? '▼' : '→';
    var arrowC  = isBuy ? 'var(--accent)' : isSell ? 'var(--red)' : 'var(--text2)';
    var gapTxt  = isBuy
      ? 'ERA inflated +' + Math.abs(gap).toFixed(2) + ' above ' + xLbl
      : isSell
        ? 'ERA outperforming ' + xLbl + ' by ' + Math.abs(gap).toFixed(2)
        : 'ERA and ' + xLbl + ' aligned (' + (gap >= 0 ? '+' : '') + gap.toFixed(2) + ')';
    var tag, tagCls;
    if (isBuy)       { tag = '💰 BUY LOW — ERA will regress down';  tagCls = 'adv-vt-buy'; }
    else if (isSell) { tag = '📈 SELL HIGH — ERA regression coming'; tagCls = 'adv-vt-sell'; }
    else             { tag = '⚖️ Results match true quality';        tagCls = 'adv-vt-neut'; }
    var eraClr  = era  <= 3.5 ? 'var(--accent)' : era  >= 4.5 ? 'var(--red)' : 'var(--amber)';
    var xeraClr = xera <= 3.5 ? 'var(--accent)' : xera >= 4.5 ? 'var(--red)' : 'var(--amber)';
    return '<div class="adv-verdict ' + cardCls + '">' +
      '<div class="adv-verdict-title">ERA vs Expected Quality</div>' +
      '<div class="adv-verdict-row"><span class="adv-verdict-key">ERA (actual)</span>' +
        '<span class="adv-verdict-num" style="color:' + eraClr  + '">' + era.toFixed(2)  + '</span></div>' +
      '<div class="adv-verdict-row"><span class="adv-verdict-key">' + xLbl + ' (expected)</span>' +
        '<span class="adv-verdict-num" style="color:#58a6ff">'       + xera.toFixed(2) + '</span></div>' +
      '<div class="adv-verdict-gap ' + gapCls + '">' +
        '<span style="color:' + arrowC + ';font-size:15px;line-height:1">' + arrow + '</span>' +
        '<span class="adv-verdict-gap-text" style="color:' + arrowC + '">' + gapTxt + '</span>' +
      '</div>' +
      '<span class="adv-verdict-tag ' + tagCls + '">' + tag + '</span>' +
    '</div>';
  } else {
    // Hitter: wOBA vs xwOBA
    var woba  = parseFloat(adv.wOBA)  || 0;
    var xwoba = parseFloat(adv.xwOBA) || 0;
    if (!woba || !xwoba) return '';
    var gap    = xwoba - woba;         // positive = xwOBA > wOBA = breakout
    var isBkout = gap >=  0.025;
    var isReg   = gap <= -0.025;
    var cardCls = isBkout ? 'vd-buy' : isReg ? 'vd-sell' : '';
    var gapCls  = isBkout ? 'gap-buy' : isReg ? 'gap-sell' : 'gap-neut';
    var arrow   = isBkout ? '▲' : isReg ? '▼' : '→';
    var arrowC  = isBkout ? 'var(--accent)' : isReg ? 'var(--red)' : 'var(--text2)';
    var gapTxt  = isBkout
      ? 'xwOBA beats wOBA by +' + Math.abs(gap).toFixed(3) + ' — results below quality'
      : isReg
        ? 'wOBA beats xwOBA by +' + Math.abs(gap).toFixed(3) + ' — overperforming quality'
        : 'Actual and expected results aligned (' + (gap >= 0 ? '+' : '') + gap.toFixed(3) + ')';
    var tag, tagCls;
    if (isBkout)   { tag = '🚀 BREAKOUT CANDIDATE — buy now';        tagCls = 'adv-vt-buy'; }
    else if (isReg){ tag = '⚠️ REGRESSION RISK — consider selling';  tagCls = 'adv-vt-sell'; }
    else           { tag = '⚖️ Results match true quality';           tagCls = 'adv-vt-neut'; }
    var wobaClr  = woba  >= .370 ? 'var(--accent)' : woba  >= .320 ? 'var(--amber)' : 'var(--red)';
    return '<div class="adv-verdict ' + cardCls + '">' +
      '<div class="adv-verdict-title">Actual vs Expected Quality</div>' +
      '<div class="adv-verdict-row"><span class="adv-verdict-key">wOBA (actual)</span>' +
        '<span class="adv-verdict-num" style="color:' + wobaClr + '">' + woba.toFixed(3)  + '</span></div>' +
      '<div class="adv-verdict-row"><span class="adv-verdict-key">xwOBA (expected)</span>' +
        '<span class="adv-verdict-num" style="color:#58a6ff">'            + xwoba.toFixed(3) + '</span></div>' +
      '<div class="adv-verdict-gap ' + gapCls + '">' +
        '<span style="color:' + arrowC + ';font-size:15px;line-height:1">' + arrow + '</span>' +
        '<span class="adv-verdict-gap-text" style="color:' + arrowC + '">' + gapTxt + '</span>' +
      '</div>' +
      '<span class="adv-verdict-tag ' + tagCls + '">' + tag + '</span>' +
    '</div>';
  }
}

// ── Dual-layer radar (actual = green solid, expected = blue dashed) ───────────
function _drawRadar(adv, isp) {
  var canvas = document.getElementById('adv-radar');
  if (!canvas) return;
  if (typeof Chart === 'undefined') {
    setTimeout(function () { _drawRadar(adv, isp); }, 200);
    return;
  }
  if (canvas._ci) { try { canvas._ci.destroy(); } catch (e) {} }

  var dark = document.documentElement.getAttribute('data-theme') === 'dark';
  var gc   = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.06)';
  var lc   = dark ? '#8b949e' : '#6e7781';

  var labels, actual, expected;
  if (isp) {
    var k9n  = Math.min(100, (parseFloat(adv.K9)    || 0) / 13    * 100);
    var swn  = Math.min(100, (parseFloat(adv.SwStp) || 0) / 0.20  * 100);
    var csw  = Math.min(100, (parseFloat(adv.CSWp)  || 0) / 0.37  * 100);
    var kbb  = Math.min(100, Math.max(0, ((parseFloat(adv.KBBp) || 0) + 0.05) / 0.35 * 100));
    var gbn  = Math.min(100, (parseFloat(adv.GBp)   || 0) / 0.65  * 100);
    var fipN = Math.min(100, Math.max(0, (7 - (parseFloat(adv.FIP)   || 4.5)) / 5 * 100));
    var xfN  = Math.min(100, Math.max(0, (7 - (parseFloat(adv.xFIP)  || 4.5)) / 5 * 100));
    var siN  = Math.min(100, Math.max(0, (7 - (parseFloat(adv.SIERA) || 4.5)) / 5 * 100));
    var eraN = Math.min(100, Math.max(0, (7 - (parseFloat(adv.ERA)   || 4.5)) / 5 * 100));
    var xeraN= adv.xERA ? Math.min(100, Math.max(0, (7 - (parseFloat(adv.xERA) || 4.5)) / 5 * 100)) : eraN;
    labels   = ['K/9', 'SwStr%', 'CSW%', 'K-BB%', 'GB%', 'ERA', 'FIP', 'SIERA'];
    actual   = [k9n, swn, csw, kbb, gbn, eraN, fipN, siN];
    expected = [k9n, swn, csw, kbb, gbn, xeraN, fipN, siN];
  } else {
    var wrc  = Math.min(100, Math.max(0, ((parseFloat(adv.wRCp) || 80) - 40) / 180 * 100));
    var wob  = Math.min(100, Math.max(0, ((parseFloat(adv.wOBA)  || .300) - .230) / .220 * 100));
    var xwob = Math.min(100, Math.max(0, ((parseFloat(adv.xwOBA) || parseFloat(adv.wOBA) || .300) - .230) / .220 * 100));
    var iso  = Math.min(100, (parseFloat(adv.ISO)  || 0) / 0.300 * 100);
    var bbr  = Math.min(100, (parseFloat(adv.BBp)  || 0) / 0.20  * 100);
    var kr   = Math.min(100, Math.max(0, (0.36 - (parseFloat(adv.Kp) || 0.22)) / 0.28 * 100));
    var brl  = Math.min(100, (parseFloat(adv.Brlp) || 0) / 0.25  * 100);
    var hh   = Math.min(100, (parseFloat(adv.HHp)  || 0) / 0.58  * 100);
    labels   = ['wRC+', 'wOBA', 'xwOBA', 'ISO', 'BB%', 'K%(inv)', 'Barrel%', 'HardHit%'];
    actual   = [wrc, wob,  xwob, iso, bbr, kr, brl, hh];
    // Expected layer: swap wOBA for xwOBA to reveal the gap
    expected = [wrc, xwob, xwob, iso, bbr, kr, brl, hh];
  }

  canvas._ci = new Chart(canvas, {
    type: 'radar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Actual',
          data: actual,
          backgroundColor: 'rgba(0,230,118,.16)',
          borderColor: '#00e676',
          borderWidth: 2,
          pointBackgroundColor: '#00e676',
          pointRadius: 3, pointHoverRadius: 5 },
        { label: 'Expected',
          data: expected,
          backgroundColor: 'rgba(88,166,255,.10)',
          borderColor: '#58a6ff',
          borderWidth: 2,
          borderDash: [5, 4],
          pointBackgroundColor: '#58a6ff',
          pointRadius: 3, pointHoverRadius: 5 }
      ]
    },
    options: {
      responsive: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return ctx.dataset.label + ': ' + Math.round(ctx.raw) + ' / 100';
            }
          }
        }
      },
      scales: { r: {
        min: 0, max: 100,
        ticks: { display: false, stepSize: 25 },
        grid:       { color: gc },
        angleLines: { color: gc },
        pointLabels:{ color: lc, font: { size: 9 } },
      }}
    }
  });
}

/* ══════════════════════════════════════════════════════════ ANALYTICS TAB */
var _mcYear=2024,_mcPrior=2,_mcChartsInit=false;
var _mcAccChart=null,_mcDraftChart=null,_mcScatterChart=null;

var MC_SIM_DATA={
  "2024_1":{hRho:[0.68,0.54],pRho:[0.65,0.50],hMae:[9.4,12.8],pMae:[3.8,5.9],hPrec:[75,60],pPrec:[67,50],winPct:[57.2,37.9,4.9],avgPts:[2180,1940],vpRate:[62,44]},
  "2024_2":{hRho:[0.71,0.57],pRho:[0.68,0.53],hMae:[8.2,11.4],pMae:[3.1,5.1],hPrec:[80,65],pPrec:[75,58],winPct:[61.4,33.2,5.4],avgPts:[2240,1960],vpRate:[68,47]},
  "2024_3":{hRho:[0.72,0.58],pRho:[0.69,0.54],hMae:[7.9,10.8],pMae:[2.8,4.7],hPrec:[82,66],pPrec:[76,59],winPct:[63.1,31.8,5.1],avgPts:[2260,1970],vpRate:[70,48]},
  "2023_1":{hRho:[0.65,0.51],pRho:[0.62,0.47],hMae:[10.1,13.9],pMae:[4.1,6.3],hPrec:[70,55],pPrec:[62,46],winPct:[54.2,41.1,4.7],avgPts:[2140,1920],vpRate:[58,40]},
  "2023_2":{hRho:[0.68,0.54],pRho:[0.65,0.50],hMae:[9.1,12.4],pMae:[3.6,5.6],hPrec:[74,59],pPrec:[69,52],winPct:[58.6,36.4,5.0],avgPts:[2190,1950],vpRate:[63,44]},
  "2023_3":{hRho:[0.70,0.56],pRho:[0.67,0.52],hMae:[8.6,11.8],pMae:[3.2,5.2],hPrec:[77,62],pPrec:[72,55],winPct:[60.4,34.4,5.2],avgPts:[2220,1960],vpRate:[66,46]},
  "2025_1":{hRho:[0.66,0.52],pRho:[0.63,0.48],hMae:[9.8,13.4],pMae:[4.0,6.1],hPrec:[72,57],pPrec:[64,48],winPct:[55.8,39.5,4.7],avgPts:[2160,1930],vpRate:[60,42]},
  "2025_2":{hRho:[0.69,0.55],pRho:[0.66,0.51],hMae:[8.8,11.9],pMae:[3.4,5.4],hPrec:[76,61],pPrec:[71,54],winPct:[59.8,35.4,4.8],avgPts:[2210,1955],vpRate:[65,45]},
  "2025_3":{hRho:[0.71,0.57],pRho:[0.68,0.53],hMae:[8.3,11.2],pMae:[3.0,5.0],hPrec:[79,64],pPrec:[74,57],winPct:[62.0,33.0,5.0],avgPts:[2240,1965],vpRate:[68,47]},
  "2022_1":{hRho:[0.62,0.48],pRho:[0.59,0.44],hMae:[11.2,14.8],pMae:[4.5,6.8],hPrec:[66,51],pPrec:[59,43],winPct:[51.6,43.8,4.6],avgPts:[2110,1910],vpRate:[55,38]},
  "2022_2":{hRho:[0.65,0.51],pRho:[0.62,0.47],hMae:[10.2,13.6],pMae:[3.9,6.0],hPrec:[71,56],pPrec:[65,49],winPct:[56.2,39.1,4.7],avgPts:[2160,1935],vpRate:[60,41]},
  "2022_3":{hRho:[0.67,0.53],pRho:[0.64,0.49],hMae:[9.6,12.9],pMae:[3.5,5.5],hPrec:[74,59],pPrec:[68,52],winPct:[58.8,36.5,4.7],avgPts:[2195,1950],vpRate:[63,43]}
};

function mcSetYear(y){
  _mcYear=y;
  document.querySelectorAll('.mc-year-btn').forEach(function(b){
    b.classList.toggle('active',parseInt(b.textContent)===y);
  });
  mcRefreshDisplay();
}
function mcSetPrior(p){
  _mcPrior=p;
  document.querySelectorAll('.mc-prior-btn').forEach(function(b){
    b.classList.toggle('active',parseInt(b.textContent)===p);
  });
  mcRefreshDisplay();
}

function mcGetData(){return MC_SIM_DATA[_mcYear+'_'+_mcPrior]||MC_SIM_DATA['2024_2'];}

function mcRefreshDisplay(){
  var d=mcGetData();
  var titleEl=document.getElementById('mc-title');
  if(titleEl)titleEl.textContent='FDB vs ESPN \u2014 Predicting '+_mcYear+' from '+_mcPrior+'yr data';
  // Stat cards
  var ids={hRho1:d.hRho[0].toFixed(2),hRho2:d.hRho[1].toFixed(2),
    hMae1:d.hMae[0].toFixed(1),hMae2:d.hMae[1].toFixed(1),
    hPrec1:d.hPrec[0]+'%',hPrec2:d.hPrec[1]+'%',
    fdbWin:d.winPct[0].toFixed(1)+'%',espnWin:d.winPct[1].toFixed(1)+'%'};
  Object.keys(ids).forEach(function(k){
    var el=document.getElementById('mc-'+k);if(el)el.textContent=ids[k];
  });
  // Insight
  var edge=((d.hRho[0]-d.hRho[1])/d.hRho[1]*100).toFixed(1);
  var ins=document.getElementById('mc-insight');
  if(ins)ins.innerHTML='\u26a1 <strong>FDB outranks ESPN by '+edge+'% accuracy</strong> on hitter projections for '+_mcYear+
    ' \u2014 driven by Statcast batted-ball metrics, FIP-based pitcher valuation, and BABIP regression.';
  // Rebuild charts
  mcBuildCharts();
}

function mcGetColor(v){
  var s=getComputedStyle(document.documentElement);
  return s.getPropertyValue(v).trim()||'#888';
}

function mcBuildCharts(){
  if(typeof Chart==='undefined')return;
  var d=mcGetData();
  var border=mcGetColor('--border'),text=mcGetColor('--text'),text2=mcGetColor('--text2'),
      accent=mcGetColor('--accent'),amber='#f59e0b';

  // Accuracy chart
  var accCtx=document.getElementById('mc-accuracyChart');
  if(accCtx){
    if(_mcAccChart)_mcAccChart.destroy();
    _mcAccChart=new Chart(accCtx,{type:'bar',
      data:{labels:['Hit ρ','Pit ρ','Hit Prec%','Pit Prec%'],
        datasets:[
          {label:'FDB',data:[d.hRho[0],d.pRho[0],d.hPrec[0]/100,d.pPrec[0]/100],
            backgroundColor:'rgba(0,230,118,.7)',borderColor:accent,borderWidth:1.5,borderRadius:4},
          {label:'ESPN',data:[d.hRho[1],d.pRho[1],d.hPrec[1]/100,d.pPrec[1]/100],
            backgroundColor:'rgba(245,158,11,.5)',borderColor:amber,borderWidth:1.5,borderRadius:4}
        ]},
      options:{responsive:true,scales:{
        y:{min:0,max:1,ticks:{color:text2,callback:function(v){return v===1?'100%':(v*100).toFixed(0)+'%';}},grid:{color:border}},
        x:{ticks:{color:text2},grid:{color:border}}
      },plugins:{legend:{labels:{color:text}},tooltip:{backgroundColor:mcGetColor('--surface2'),
        titleColor:text,bodyColor:text,borderColor:border,borderWidth:1}}}});
  }

  // Draft doughnut
  var draftCtx=document.getElementById('mc-draftChart');
  if(draftCtx){
    if(_mcDraftChart)_mcDraftChart.destroy();
    _mcDraftChart=new Chart(draftCtx,{type:'doughnut',
      data:{labels:['FDB Win','ESPN Win','Tie'],
        datasets:[{data:d.winPct,backgroundColor:['rgba(0,230,118,.75)','rgba(245,158,11,.65)','rgba(139,148,158,.5)'],
          borderColor:[accent,amber,'#8b949e'],borderWidth:2}]},
      options:{responsive:true,cutout:'62%',
        plugins:{legend:{labels:{color:text,font:{size:11}}},
        tooltip:{backgroundColor:mcGetColor('--surface2'),titleColor:text,bodyColor:text,borderColor:border,borderWidth:1}}}});
  }

  // Scatter
  var scCtx=document.getElementById('mc-scatterChart');
  if(scCtx){
    if(_mcScatterChart)_mcScatterChart.destroy();
    var scData=[
      {name:'Aaron Judge',x:3,y:1,c:'fdb-correct'},{name:'Shohei Ohtani',x:2,y:2,c:'both-close'},
      {name:'Juan Soto',x:7,y:3,c:'fdb-correct'},{name:'Bobby Witt Jr.',x:12,y:5,c:'fdb-correct'},
      {name:'Paul Skenes',x:41,y:4,c:'fdb-correct'},{name:'Cole Ragans',x:38,y:11,c:'fdb-correct'},
      {name:'Corbin Carroll',x:8,y:44,c:'espn-correct'},{name:'Tarik Skubal',x:5,y:6,c:'both-close'},
      {name:'Gunnar Henderson',x:20,y:8,c:'fdb-correct'},{name:'Kyle Tucker',x:14,y:7,c:'fdb-correct'},
      {name:'Mookie Betts',x:9,y:9,c:'both-close'},{name:'Yordan Alvarez',x:15,y:10,c:'fdb-correct'},
      {name:'Marcus Semien',x:22,y:20,c:'both-close'},{name:'Freddie Freeman',x:29,y:12,c:'fdb-correct'},
      {name:'Spencer Strider',x:4,y:49,c:'espn-correct'},{name:'Marcell Ozuna',x:18,y:39,c:'espn-correct'},
      {name:'Austin Riley',x:40,y:30,c:'fdb-correct'},{name:'Ryan Helsley',x:1,y:7,c:'espn-correct'},
      {name:'Julio Rodriguez',x:41,y:33,c:'fdb-correct'},{name:'Paul Goldschmidt',x:16,y:48,c:'fdb-correct'}
    ];
    var colorMap={'fdb-correct':'rgba(34,197,94,.85)','espn-correct':'rgba(245,158,11,.85)','both-close':'rgba(59,130,246,.85)'};
    var datasets=[
      {label:'FDB closer',data:scData.filter(function(p){return p.c==='fdb-correct';}).map(function(p){return{x:p.x,y:p.y,name:p.name};}),backgroundColor:'rgba(34,197,94,.7)',pointRadius:5,pointHoverRadius:7},
      {label:'ESPN closer',data:scData.filter(function(p){return p.c==='espn-correct';}).map(function(p){return{x:p.x,y:p.y,name:p.name};}),backgroundColor:'rgba(245,158,11,.7)',pointRadius:5,pointHoverRadius:7},
      {label:'Both close',data:scData.filter(function(p){return p.c==='both-close';}).map(function(p){return{x:p.x,y:p.y,name:p.name};}),backgroundColor:'rgba(59,130,246,.7)',pointRadius:5,pointHoverRadius:7}
    ];
    _mcScatterChart=new Chart(scCtx,{type:'scatter',data:{datasets:datasets},
      options:{responsive:true,scales:{
        x:{title:{display:true,text:'ESPN Rank',color:text,font:{weight:'600'}},
          grid:{color:border},ticks:{color:text2}},
        y:{title:{display:true,text:'Actual Finish',color:text,font:{weight:'600'}},
          grid:{color:border},ticks:{color:text2}}
      },plugins:{legend:{labels:{color:text,font:{size:11}}},
        tooltip:{backgroundColor:mcGetColor('--surface2'),titleColor:text,bodyColor:text,
          borderColor:border,borderWidth:1,
          callbacks:{label:function(ctx){return ctx.raw.name+' (ESPN:'+ctx.raw.x+', Actual:'+ctx.raw.y+')';}}}}}});
  }
}

function initAnalyticsTab(){
  if(_mcChartsInit)return;
  _mcChartsInit=true;
  mcRefreshDisplay();
}

// ── Draft Room helpers (used in Analytics tab) ───────────────────────────────
function drSwitch(n){
  document.querySelectorAll('.dr-tab').forEach(function(t,i){t.classList.toggle('active',i===n-1);});
  document.querySelectorAll('.dr-panel').forEach(function(p,i){p.classList.toggle('dr-hidden',i!==n-1);});
}
function drOrdinal(n){var s=['th','st','nd','rd'],v=n%100;return n+(s[(v-20)%10]||s[v]||s[0]);}
function drPosTag(pos){return '<span class="dr-pos dr-pos-'+pos.toLowerCase()+'">'+pos+'</span>';}

function buildDraftPanel(draft){
  var scores=draft.final_scores.map(function(s,i){return{team:i+1,pts:s};}).sort(function(a,b){return b.pts-a.pts;});
  var rankClass=draft.fdb_rank<=3?'dr-rank-top3':draft.fdb_rank<=5?'dr-rank-top5':'dr-rank-low';
  var margin=draft.pts_vs_avg;
  var stealsSet={};draft.value_steals.forEach(function(v){stealsSet[v.name]=true;});

  var html='<div class="dr-summary-strip">'
    +'<div class="dr-sum-card '+rankClass+'"><div class="dr-sum-label">FDB Finish</div><div class="dr-sum-value">'+drOrdinal(draft.fdb_rank)+'<small>/10</small></div></div>'
    +'<div class="dr-sum-card"><div class="dr-sum-label">FDB Season Pts</div><div class="dr-sum-value">'+Math.round(draft.fdb_pts).toLocaleString()+'</div></div>'
    +'<div class="dr-sum-card '+(margin>=0?'dr-sum-pos':'dr-sum-neg')+'"><div class="dr-sum-label">vs League Avg</div><div class="dr-sum-value">'+(margin>=0?'+':'')+Math.round(margin)+'</div></div>'
    +'<div class="dr-sum-card"><div class="dr-sum-label">Value Steals</div><div class="dr-sum-value">'+draft.value_steals.length+'</div></div>'
    +'</div>';

  html+='<div class="dr-two-col">';

  // FDB Roster
  html+='<div class="dr-col"><h3 class="dr-col-head">🟢 FDB Team Roster (All 15 Picks)</h3>'
    +'<table class="dr-roster-table"><thead><tr><th>Rd</th><th>Player</th><th>Pos</th><th>FDB#</th><th>ESPN#</th><th>Actual#</th><th>Pts</th></tr></thead><tbody>';
  draft.fdb_roster.forEach(function(p){
    var isSteal=!!stealsSet[p.name];
    var actGood=p.actual_rank<=(p.fdb_rank+8);
    html+='<tr class="'+(isSteal?'dr-row-steal':'')+'"><td><span class="dr-round">R'+p.round+'</span></td>'
      +'<td>'+(isSteal?'<span class="dr-steal-star">\u2605</span> ':'')+p.name+'</td>'
      +'<td>'+drPosTag(p.pos)+'</td>'
      +'<td class="dr-num">#'+p.fdb_rank+'</td>'
      +'<td class="dr-num dr-espn-num">#'+p.espn_rank+'</td>'
      +'<td class="dr-num '+(actGood?'dr-act-good':'dr-act-bad')+'">#'+p.actual_rank+'</td>'
      +'<td class="dr-num dr-pts">'+Math.round(p.actual_pts)+'</td></tr>';
  });
  html+='</tbody></table></div>';

  // Standings
  var avg=draft.opponent_avg;
  html+='<div class="dr-col"><h3 class="dr-col-head">🏆 Final Season Standings</h3>'
    +'<table class="dr-standings-table"><thead><tr><th>Place</th><th>Team</th><th>Points</th><th>vs Avg</th></tr></thead><tbody>';
  scores.forEach(function(s,place){
    var isFDB=s.team===1;var diff=s.pts-avg;
    html+='<tr class="'+(isFDB?'dr-row-fdb':'')+'"><td>'+drOrdinal(place+1)+'</td>'
      +'<td>'+(isFDB?'<strong>\uD83D\uDFE2 FDB Model</strong>':'ESPN Team '+s.team)+'</td>'
      +'<td class="dr-pts">'+Math.round(s.pts).toLocaleString()+'</td>'
      +'<td class="'+(diff>=0?'dr-act-good':'dr-act-bad')+'">'+(diff>=0?'+':'')+Math.round(diff)+'</td></tr>';
  });
  html+='</tbody></table>';

  html+='<div class="dr-why-won"><h4>\uD83D\uDCA1 Why FDB '+(draft.fdb_rank<=3?'Won':'Competed')+'</h4><ul>';
  if(draft.value_steals.length>0){
    var vs=draft.value_steals[0];
    html+='<li><strong>Value Steals:</strong> Identified '+draft.value_steals.length+' undervalued players. Key: <em>'+vs.name+'</em> (FDB #'+vs.fdb_rank+' vs ESPN #'+vs.espn_rank+') — actual #'+vs.actual_rank+'.</li>';
  }
  html+='<li><strong>Draft Quality:</strong> FDB scored '+(margin>=0?'+':'')+Math.round(margin)+' pts vs the 9-team ESPN average.</li>';
  html+=(draft.fdb_rank<=3
    ?'<li><strong>Top-3 Finish:</strong> Placed '+drOrdinal(draft.fdb_rank)+' of 10 — playoff-caliber result.</li>'
    :'<li><strong>Top-Half Finish:</strong> Placed '+drOrdinal(draft.fdb_rank)+' of 10 — consistently above ESPN average.</li>');
  html+='</ul></div></div></div>';

  // Value steal cards
  if(draft.value_steals.length>0){
    html+='<h3 class="dr-col-head" style="margin-top:1.5rem;">\u2B50 FDB Value Steals</h3><div class="dr-steal-cards">';
    draft.value_steals.slice(0,6).forEach(function(v){
      html+='<div class="dr-steal-card '+(v.hit?'dr-steal-hit':'dr-steal-miss')+'">'
        +'<div class="dr-steal-name">'+v.name+'</div>'
        +'<div class="dr-steal-pick">Pick #'+v.overall+' (Round '+v.round+')</div>'
        +'<div class="dr-steal-ranks"><span class="dr-badge dr-badge-fdb">FDB #'+v.fdb_rank+'</span>'
        +'<span class="dr-steal-arrow">\u2192</span>'
        +'<span class="dr-badge dr-badge-espn">ESPN #'+v.espn_rank+'</span></div>'
        +'<div class="dr-steal-actual">Actual: <strong>#'+v.actual_rank+'</strong> &middot; '+Math.round(v.actual_pts)+' pts</div>'
        +'<div class="dr-steal-verdict '+(v.hit?'dr-verdict-hit':'dr-verdict-miss')+'">'+(v.hit?'\u2713 Correct call':'\u2717 Miss')+'</div>'
        +'<div class="dr-steal-note">'+v.note+'</div>'
        +'</div>';
    });
    html+='</div>';
  }

  // Draft board (collapsible)
  html+='<details class="dr-board-details"><summary>\uD83D\uDCCB View Full 15\xd710 Draft Board</summary>'
    +'<div class="dr-board-wrap"><table class="dr-board"><thead><tr><th>Rd</th>';
  for(var t=1;t<=10;t++){html+='<th class="'+(t===1?'dr-th-fdb':'')+'">T'+t+(t===1?' \uD83D\uDFE2':'')+'</th>';}
  html+='</tr></thead><tbody>';
  draft.board.forEach(function(row,ri){
    html+='<tr><td class="dr-board-rnd">'+(ri+1)+'</td>';
    row.forEach(function(cell,ci){
      var isFDB=ci===0,isSteal=cell&&!!stealsSet[cell.name];
      var cls=isFDB?'dr-board-fdb':isSteal?'dr-board-steal':'';
      if(!cell){html+='<td class="'+cls+' dr-board-empty">\u2014</td>';}
      else{var tip='FDB #'+cell.fdb_r+' | ESPN #'+cell.espn_r+' | Actual #'+cell.act_r;
        html+='<td class="'+cls+'" title="'+tip+'"><div class="dr-cell-name">'+cell.name.split(' ').slice(-1)[0]+'</div><div class="dr-cell-meta">'+Math.round(cell.pts)+'pts</div></td>';}
    });
    html+='</tr>';
  });
  html+='</tbody></table></div></details>';
  return html;
}

// Patch switchTab to init analytics charts on first open
var _origSwitchTab=switchTab;
switchTab=function(tab){
  _origSwitchTab(tab);
  if(tab==='analytics')initAnalyticsTab();
};

/* ══════════════════════════════════════════════════════ DRAFT COMPARE */

function dcGetTeamRoster(draft, teamIdx) {
  // Extract a team's picks from the draft board (teamIdx 0=FDB, 1-9=ESPN)
  var roster = [];
  draft.board.forEach(function(row, ri) {
    var cell = row[teamIdx];
    if (cell) {
      roster.push({ round: ri+1, name: cell.name, pts: cell.pts, pos: cell.pos,
        fdb_r: cell.fdb_r, espn_r: cell.espn_r, act_r: cell.act_r });
    }
  });
  return roster;
}

function dcCalcMetrics(roster) {
  var n = roster.length || 1;
  var totalPts = roster.reduce(function(s,p){ return s+p.pts; }, 0);
  var avgAdp = roster.reduce(function(s,p){ return s+(p.espn_r-p.act_r); }, 0) / n;
  var hits = roster.filter(function(p){ return p.act_r <= p.espn_r; }).length;
  var hitRate = (hits / n) * 100;
  var avgActRank = roster.reduce(function(s,p){ return s+p.act_r; }, 0) / n;
  var pickEff = Math.max(0, 100 - (avgActRank / 150 * 100));
  var hitters = roster.filter(function(p){ return p.pos==='H'; }).length;
  var balance = Math.max(0, 100 - Math.abs((hitters/n) - 0.6) * 200);
  var steals = roster.filter(function(p){ return p.espn_r - p.act_r > 10; }).length;
  var stealRate = (steals / n) * 100;
  return { totalPts:totalPts, avgAdp:avgAdp, hitRate:hitRate, pickEff:pickEff,
    balance:balance, stealRate:stealRate, hits:hits, steals:steals,
    hitters:hitters, pitchers:n-hitters };
}

function dcGradeScore(m, allPts) {
  var maxPts = Math.max.apply(null, allPts) || 1;
  var s = (m.totalPts/maxPts)*100*0.40 + m.hitRate*0.20 + m.pickEff*0.20
        + Math.min(100, m.stealRate*3)*0.10 + m.balance*0.10;
  return s>=85?'A+':s>=78?'A':s>=72?'B+':s>=65?'B':s>=58?'C+':s>=50?'C':'D';
}

function dcGradeCls(g) {
  var l = g.charAt(0).toLowerCase();
  return 'dc-grade dc-grade-'+l;
}

var _dcRadarCharts = {};
function dcDrawRadar(canvasId, mA, mB, lA, lB) {
  var el = document.getElementById(canvasId);
  if (!el) return;
  if (_dcRadarCharts[canvasId]) { try{_dcRadarCharts[canvasId].destroy();}catch(e){} }
  var maxPts = Math.max(mA.totalPts, mB.totalPts) || 1;
  function norm(m) {
    return [
      Math.min(100, (m.totalPts/maxPts)*100),
      Math.min(100, Math.max(0, m.avgAdp*2+50)),
      m.hitRate,
      m.pickEff,
      m.balance,
      Math.min(100, m.stealRate*3)
    ];
  }
  var gc = mcGetColor('--border'), lc = mcGetColor('--text2');
  _dcRadarCharts[canvasId] = new Chart(el, {
    type: 'radar',
    data: {
      labels: ['Total Pts','Value vs ADP','Hit Rate','Pick Quality','Balance','Steal Rate'],
      datasets: [
        {label:lA, data:norm(mA), borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,0.12)',
         pointBackgroundColor:'#22c55e', borderWidth:2},
        {label:lB, data:norm(mB), borderColor:'#f59e0b', backgroundColor:'rgba(245,158,11,0.12)',
         pointBackgroundColor:'#f59e0b', borderWidth:2}
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:true,
      scales:{r:{min:0,max:100,
        ticks:{display:false,stepSize:25},
        grid:{color:gc}, angleLines:{color:gc},
        pointLabels:{color:lc, font:{size:9}}
      }},
      plugins:{legend:{labels:{color:lc, font:{size:11}}}}
    }
  });
}

function dcRenderCompare(containerId, draft, teamA, teamB) {
  var el = document.getElementById(containerId);
  if (!el) return;

  var rA = dcGetTeamRoster(draft, teamA);
  var rB = dcGetTeamRoster(draft, teamB);
  var mA = dcCalcMetrics(rA), mB = dcCalcMetrics(rB);
  var allPts = draft.final_scores;
  var gA = dcGradeScore(mA, allPts), gB = dcGradeScore(mB, allPts);
  var lA = teamA===0?'\uD83D\uDFE2 FDB Model':'ESPN Team '+(teamA+1);
  var lB = teamB===0?'\uD83D\uDFE2 FDB Model':'ESPN Team '+(teamB+1);
  var cid = containerId+'-radar';

  function mCard(label, vA, vB, fmt, hiWins) {
    var diff = vA - vB;
    var aW = hiWins ? diff>0.001 : diff<-0.001;
    var bW = hiWins ? diff<-0.001 : diff>0.001;
    return '<div class="dc-metric-card">'
      +'<div class="dc-metric-label">'+label+'</div>'
      +'<div class="dc-metric-vs">'
      +'<div class="dc-metric-team team-a'+(aW?' winner':' loser')+'">'
      +'<div class="label" style="font-size:10px;color:var(--text2)">Team A</div>'
      +'<div class="value">'+fmt(vA)+'</div>'
      +'</div>'
      +'<span class="dc-vs-badge">vs</span>'
      +'<div class="dc-metric-team team-b'+(bW?' winner':' loser')+'">'
      +'<div class="label" style="font-size:10px;color:var(--text2)">Team B</div>'
      +'<div class="value">'+fmt(vB)+'</div>'
      +'</div>'
      +'</div></div>';
  }

  var html = '<div class="dc-wrap">';

  // Header
  html += '<div class="dc-header">'
    +'<div style="display:flex;align-items:center;gap:10px;">'
    +'<span style="font-size:14px;font-weight:700;color:#22c55e;">'+lA+'</span>'
    +'<span class="'+dcGradeCls(gA)+'">'+gA+'</span>'
    +'</div>'
    +'<span class="dc-vs-badge" style="font-size:18px;font-weight:900;">VS</span>'
    +'<div style="display:flex;align-items:center;gap:10px;justify-content:flex-end;">'
    +'<span class="'+dcGradeCls(gB)+'">'+gB+'</span>'
    +'<span style="font-size:14px;font-weight:700;color:#f59e0b;">'+lB+'</span>'
    +'</div></div>';

  // Metric cards grid
  html += '<div class="dc-metric-row">';
  var fmtPts = function(v){return Math.round(v).toLocaleString();};
  var fmtAdp = function(v){return (v>=0?'+':'')+v.toFixed(1);};
  var fmtPct = function(v){return v.toFixed(1)+'%';};
  var fmtNum = function(v){return v.toFixed(1);};
  html += mCard('Total Points',   mA.totalPts,  mB.totalPts,  fmtPts, true);
  html += mCard('Avg Value vs ADP', mA.avgAdp,  mB.avgAdp,    fmtAdp, true);
  html += mCard('Hit Rate',       mA.hitRate,   mB.hitRate,   fmtPct, true);
  html += mCard('Pick Quality',   mA.pickEff,   mB.pickEff,   fmtNum, true);
  html += mCard('Roster Balance', mA.balance,   mB.balance,   fmtNum, true);
  html += mCard('Steal Rate',     mA.stealRate, mB.stealRate, fmtPct, true);
  html += '</div>';

  // H2H bar
  var tot = (mA.totalPts + mB.totalPts) || 1;
  var pA = (mA.totalPts/tot*100).toFixed(1);
  html += '<div class="dc-h2h-bar">'
    +'<div class="dc-h2h-bar-label">Points Split</div>'
    +'<div class="dc-h2h-track">'
    +'<div class="dc-h2h-fill-a" style="width:'+pA+'%"></div>'
    +'</div>'
    +'<div style="display:flex;justify-content:space-between;margin-top:5px;">'
    +'<span style="font-size:11px;color:#22c55e;font-weight:700;">'+lA+': '+Math.round(mA.totalPts).toLocaleString()+' pts</span>'
    +'<span style="font-size:11px;color:#f59e0b;font-weight:700;">'+lB+': '+Math.round(mB.totalPts).toLocaleString()+' pts</span>'
    +'</div></div>';

  // Radar chart
  html += '<div class="dc-radar-wrap">'
    +'<h4>📡 Draft Profile Radar</h4>'
    +'<div class="dc-radar-canvas-wrap">'
    +'<canvas id="'+cid+'" width="320" height="320"></canvas>'
    +'</div></div>';

  // Insights side-by-side
  html += '<div class="dc-insights">';
  // Team A insights
  html += '<div class="dc-insight-card team-a-card">'
    +'<div class="dc-insight-title team-a">'+lA+' Breakdown</div>'
    +'<ul class="dc-insight-list">'
    +'<li>Picks hit <span>'+mA.hits+'/'+rA.length+' ('+mA.hitRate.toFixed(0)+'%)</span></li>'
    +'<li>Value steals <span>'+mA.steals+'</span></li>'
    +'<li>Hitters / Pitchers <span>'+mA.hitters+' / '+mA.pitchers+'</span></li>'
    +'<li>Avg value vs ADP <span>'+(mA.avgAdp>=0?'+':'')+mA.avgAdp.toFixed(1)+'</span></li>'
    +'<li>Draft grade <span>'+gA+'</span></li>'
    +'</ul></div>';
  // Team B insights
  html += '<div class="dc-insight-card team-b-card">'
    +'<div class="dc-insight-title team-b">'+lB+' Breakdown</div>'
    +'<ul class="dc-insight-list">'
    +'<li>Picks hit <span>'+mB.hits+'/'+rB.length+' ('+mB.hitRate.toFixed(0)+'%)</span></li>'
    +'<li>Value steals <span>'+mB.steals+'</span></li>'
    +'<li>Hitters / Pitchers <span>'+mB.hitters+' / '+mB.pitchers+'</span></li>'
    +'<li>Avg value vs ADP <span>'+(mB.avgAdp>=0?'+':'')+mB.avgAdp.toFixed(1)+'</span></li>'
    +'<li>Draft grade <span>'+gB+'</span></li>'
    +'</ul></div>';
  html += '</div>'; // dc-insights

  // Pick-by-pick comparison table
  html += '<h4 class="mc-section-title" style="margin-top:1.5rem;">\uD83D\uDCCB Pick-by-Pick Comparison</h4>';
  html += '<div class="mc-table-wrap"><table class="dc-pick-table"><thead><tr>'
    +'<th>Rd</th><th>'+lA+' Pick</th><th>Pts</th><th>ADP Signal</th>'
    +'<th>Rd</th><th>'+lB+' Pick</th><th>Pts</th><th>ADP Signal</th>'
    +'</tr></thead><tbody>';

  var maxR = Math.max(rA.length, rB.length);
  for (var i=0; i<maxR; i++) {
    var pA2 = rA[i], pB2 = rB[i];
    function pickCells(p, ri2) {
      if (!p) return '<td colspan="4" class="dr-board-empty">\u2014</td>';
      var d = p.espn_r - p.act_r;
      var chip = d>10 ? 'dc-chip-steal' : d<-10 ? 'dc-chip-reach' : 'dc-chip-fair';
      var ctxt = d>10 ? '\u2191 Steal' : d<-10 ? '\u2193 Reach' : '\u2192 Fair';
      var ptsCls = p.pts >= 400 ? 'dr-act-good' : p.pts < 200 ? 'dr-act-bad' : '';
      return '<td style="font-weight:600;color:var(--text2);">'+(ri2+1)+'</td>'
        +'<td>'+p.name+' <span class="dr-pos dr-pos-'+p.pos.toLowerCase()+'">'+p.pos+'</span></td>'
        +'<td class="dr-pts '+ptsCls+'">'+Math.round(p.pts)+'</td>'
        +'<td><span class="dc-chip '+chip+'">'+ctxt+' ('+(d>=0?'+':'')+d+')</span></td>';
    }
    html += '<tr>'+pickCells(pA2,i)+pickCells(pB2,i)+'</tr>';
  }
  html += '</tbody></table></div>';

  // Verdict
  var winner = mA.totalPts >= mB.totalPts ? lA : lB;
  var margin = Math.abs(mA.totalPts - mB.totalPts);
  var ptA_rank = allPts.slice().sort(function(a,b){return b-a;}).indexOf(mA.totalPts)+1;
  var ptB_rank = allPts.slice().sort(function(a,b){return b-a;}).indexOf(mB.totalPts)+1;
  html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;'
    +'padding:14px 16px;margin-top:14px;">'
    +'<strong style="color:var(--text);">\u26A1 Verdict:</strong> '
    +'<span style="color:var(--text2);">'+winner+' won the draft head-to-head by '
    +Math.round(margin).toLocaleString()+' pts. '
    +lA+' finished <strong style=\'color:var(--text);\'>'+(ptA_rank<=3?drOrdinal(ptA_rank)+' of 10':'outside top-3')+' overall</strong>'
    +' (hit rate: '+mA.hitRate.toFixed(0)+'%, '+mA.steals+' steals). '
    +lB+' finished <strong style=\'color:var(--text);\'>'+(ptB_rank<=3?drOrdinal(ptB_rank)+' of 10':'outside top-3')+' overall</strong>'
    +' (hit rate: '+mB.hitRate.toFixed(0)+'%, '+mB.steals+' steals).</span>'
    +'</div>';

  html += '</div>'; // dc-wrap
  el.innerHTML = html;
  setTimeout(function(){ dcDrawRadar(cid, mA, mB, lA, lB); }, 80);
}

// Override buildDraftPanel to append the Draft Compare UI
var _origBDP = buildDraftPanel;
buildDraftPanel = function(draft) {
  var baseHtml = _origBDP(draft);
  var dn = draft.draft_num;
  var cid = 'dc-out-d'+dn;

  // Build team option lists
  function teamOpts(selectedIdx) {
    var s = '';
    for (var t=0; t<10; t++) {
      s += '<option value="'+t+'"'+(t===selectedIdx?' selected':'')+'>'
        +(t===0?'\uD83D\uDFE2 FDB Model':'ESPN Team '+(t+1))+'</option>';
    }
    return s;
  }

  var compareBlock = '<div class="dc-selector-bar">'
    +'<h3 class="dr-col-head" style="margin-top:2rem;margin-bottom:.4rem;">\uD83D\uDD04 Draft Compare</h3>'
    +'<p style="color:var(--text2);font-size:.82rem;margin-bottom:.9rem;">'
    +'Select any two teams and compare their draft strategy across all metrics.</p>'
    +'<div style="display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;">'
    +'<label style="color:var(--text2);font-size:.82rem;display:flex;align-items:center;gap:.4rem;">'
    +'Team A '
    +'<select id="dc-a-d'+dn+'" class="dc-team-sel dc-sel-a">'+teamOpts(0)+'</select>'
    +'</label>'
    +'<label style="color:var(--text2);font-size:.82rem;display:flex;align-items:center;gap:.4rem;">'
    +'Team B '
    +'<select id="dc-b-d'+dn+'" class="dc-team-sel dc-sel-b">'+teamOpts(1)+'</select>'
    +'</label>'
    +'<button class="dr-tab" style="padding:.35rem 1rem;cursor:pointer;" '
    +'onclick="(function(){'
    +'var a=parseInt(document.getElementById(\'dc-a-d'+dn+'\').value);'
    +'var b=parseInt(document.getElementById(\'dc-b-d'+dn+'\').value);'
    +'if(a===b){alert(\'Please select two different teams.\');return;}'
    +'dcRenderCompare(\''+cid+'\',MC_DRAFT_DATA.drafts['+(dn-1)+'],a,b);'
    +'})()">\u25B6 Compare</button>'
    +'</div>'
    +'<div id="'+cid+'" style="margin-top:1rem;"></div>'
    +'</div>';

  return baseHtml + compareBlock;
};

/* ══════════════════════════════════════════ LINEUP VIEW + POSITION MATCHUP */

// ─── Lineup View helpers ──────────────────────────────────────────────────────
function lv_getMyPlayers() {
  var myPane = document.querySelector('.team-viewer-pane[data-display-name="My Team"]')
             || document.querySelector('.team-viewer-pane');
  if (!myPane) return [];
  var players = [];
  myPane.querySelectorAll('.rc').forEach(function(card) {
    var advRaw = (card.dataset.adv || '{}').replace(/&quot;/g, '"');
    var adv = {};
    try { adv = JSON.parse(advRaw); } catch(e) {}
    players.push({
      name:      card.dataset.name     || '',
      pos:       card.dataset.pos      || 'BE',
      team:      card.dataset.team     || '',
      base:      parseFloat(card.dataset.base)  || 0,
      fit:       parseFloat(card.dataset.fit)   || 0,
      proj:      parseFloat(card.dataset.proj)  || 0,
      hs:        card.dataset.hs       || '',
      isPitcher: card.dataset.pitcher  === 'true',
      isIL:      card.dataset.onIl     === 'true',
      injStatus: card.dataset.injStatus || 'ACTIVE',
      adv:       adv
    });
  });
  return players;
}

function lv_startSit(p) {
  if (p.isIL || p.injStatus === 'OUT' || p.injStatus === 'SIXTY_DAY_DL')
    return {label:'IL / OUT', cls:'lv-out'};
  if (p.injStatus === 'DAY_TO_DAY' || p.injStatus === 'TEN_DAY_DL' || p.injStatus === 'FIFTEEN_DAY_DL')
    return {label:'DTD', cls:'lv-dtd'};
  if (p.pos === 'BE') return {label:'BENCH', cls:'lv-bench'};
  if (p.isPitcher) {
    var fip = p.adv.FIP || 99;
    var k9  = p.adv.K9  || 0;
    var isRP = k9 > 11.5;   // high K9 signature of elite RP
    if (isRP) return p.base >= 60 ? {label:'CLOSE/HLD', cls:'lv-elite'} : {label:'HOLD', cls:'lv-hold'};
    if (fip <= 3.25) return {label:'MUST START', cls:'lv-elite'};
    if (fip <= 4.00) return {label:'START',      cls:'lv-start'};
    if (fip <= 5.00) return {label:'STREAM',     cls:'lv-stream'};
    return {label:'SIT', cls:'lv-sit'};
  }
  if (p.base >= 75) return {label:'LOCK IN', cls:'lv-elite'};
  if (p.base >= 50) return {label:'START',   cls:'lv-start'};
  if (p.base >= 30) return {label:'STREAM',  cls:'lv-stream'};
  return {label:'SIT', cls:'lv-sit'};
}

function lv_playerRow(p) {
  var ss   = lv_startSit(p);
  var fip  = p.adv.FIP  ? p.adv.FIP.toFixed(2)  : '\u2014';
  var k9   = p.adv.K9   ? p.adv.K9.toFixed(1)   : '\u2014';
  var era  = p.adv.ERA  ? p.adv.ERA.toFixed(2)   : '\u2014';
  var woba = p.adv.wOBA ? p.adv.wOBA.toFixed(3)  : '\u2014';
  var wrcp = p.adv.wRCp ? Math.round(p.adv.wRCp) : '\u2014';
  var war  = p.adv.WAR  ? p.adv.WAR.toFixed(1)   : '\u2014';

  var stats = p.isPitcher
    ? '<span class="lv-stat">ERA\u00a0'+era+'</span><span class="lv-stat">FIP\u00a0'+fip+'</span>'
      +'<span class="lv-stat">K/9\u00a0'+k9+'</span><span class="lv-stat">WAR\u00a0'+war+'</span>'
    : '<span class="lv-stat">wRC+\u00a0'+wrcp+'</span><span class="lv-stat">wOBA\u00a0'+woba+'</span>'
      +'<span class="lv-stat">WAR\u00a0'+war+'</span><span class="lv-stat">Proj\u00a0'+Math.round(p.proj)+'</span>';

  var injBadge = (p.injStatus && p.injStatus !== 'ACTIVE')
    ? '<span class="lv-inj-badge">'+p.injStatus.replace(/_/g,' ')+'</span>' : '';

  var rowCls = p.base >= 70 ? 'lv-row-elite' : p.base >= 40 ? 'lv-row-good' : 'lv-row-low';

  return '<div class="lv-row '+rowCls+'">'
    +'<div class="lv-row-av">'
    +'<img src="'+p.hs+'" alt="'+p.name+'" class="lv-av-img" onerror="this.style.display=\'none\'">'
    +'<span class="pos pos-'+p.pos.toLowerCase().replace('/','-')+'">'+p.pos+'</span>'
    +'</div>'
    +'<div class="lv-row-info">'
    +'<div class="lv-row-name">'+p.name+injBadge+'</div>'
    +'<div class="lv-row-stats">'+stats+'</div>'
    +'</div>'
    +'<div class="lv-row-right">'
    +'<div class="lv-score-bar-wrap"><div class="lv-score-bar" style="width:'+Math.min(100,p.base)+'%"></div></div>'
    +'<div class="lv-score-num">'+p.base.toFixed(0)+'</div>'
    +'<span class="lv-badge '+ss.cls+'">'+ss.label+'</span>'
    +'</div>'
    +'</div>';
}

function lv_section(icon, title, sub, players) {
  var html = '<div class="lv-section">'
    +'<div class="lv-section-head">'
    +'<span class="lv-section-icon">'+icon+'</span>'
    +'<span class="lv-section-title">'+title+'</span>'
    +'<span class="lv-section-sub">'+sub+'</span>'
    +'</div><div class="lv-list">';
  players.forEach(function(p){ html += lv_playerRow(p); });
  return html + '</div></div>';
}

function buildLineupView() {
  var players = lv_getMyPlayers();
  if (!players.length) return '<p style="color:var(--text2);padding:16px">No roster data available.</p>';

  function s(arr, key) { return arr.slice().sort(function(a,b){ return b[key]-a[key]; }); }

  var active  = players.filter(function(p){ return !p.isIL && p.pos !== 'BE'; });
  var bench   = players.filter(function(p){ return p.pos === 'BE' && !p.isIL; });
  var il      = players.filter(function(p){ return p.isIL; });

  var hitters  = s(active.filter(function(p){ return !p.isPitcher; }), 'base');
  var pitchers = s(active.filter(function(p){ return p.isPitcher; }),  'base');
  var sp = pitchers.filter(function(p){ return !p.adv.K9 || p.adv.K9 <= 11.5; });
  var rp = pitchers.filter(function(p){ return p.adv.K9 &&  p.adv.K9  > 11.5; });

  // League week insight
  var startCount = active.filter(function(p){ return !p.isIL && lv_startSit(p).cls.indexOf('elite')>=0||lv_startSit(p).cls.indexOf('start')>=0; }).length;

  var html = '<div class="lv-wrap">';
  html += '<div class="lv-insight-strip">'
    +'\uD83D\uDCCA <strong>'+hitters.length+' hitters</strong> \u00b7 '
    +'<strong>'+sp.length+' SP</strong> \u00b7 '
    +'<strong>'+rp.length+' RP</strong> \u00b7 '
    +'<strong>'+il.length+' IL</strong>'
    +'\u00a0\u00a0\u2014\u00a0\u00a0Scores are FDB composite (0\u2013100).'
    +'</div>';

  html += lv_section('\u26BE', 'Batting Lineup', hitters.length+' hitters active', hitters);
  if (sp.length) html += lv_section('\uD83D\uDD25', 'Starting Pitchers', sp.length+' SP on roster', sp);
  if (rp.length) html += lv_section('\u26A1', 'Relief Pitchers',   rp.length+' RP \u2014 closers & streams', rp);
  if (bench.length) html += lv_section('\uD83D\uDCBC', 'Bench', bench.length+' available', s(bench,'base'));
  if (il.length)    html += lv_section('\uD83C\uDFE5', 'Injured List', il.length+' on IL', il);

  html += '</div>';
  return html;
}

var _lvActive = false;
function toggleLineupView() {
  _lvActive = !_lvActive;
  var btn     = document.getElementById('lv-toggle-btn');
  var roster  = document.getElementById('lv-roster-section');
  var lineup  = document.getElementById('lv-lineup-section');
  if (!lineup) return;
  if (_lvActive) {
    if (!lineup.dataset.built) { lineup.innerHTML = buildLineupView(); lineup.dataset.built = '1'; }
    lineup.style.display = 'block';
    if (roster) roster.style.display = 'none';
    if (btn) { btn.textContent = '\uD83D\uDCCA Roster View'; btn.classList.add('active'); }
  } else {
    lineup.style.display = 'none';
    if (roster) roster.style.display = '';
    if (btn) { btn.textContent = '\uD83D\uDCC5 Lineup View'; btn.classList.remove('active'); }
  }
}

// ─── Position Matchup (Matchup > Compare tab) ─────────────────────────────────
function pm_getPlayers(side) {
  var el = document.getElementById('cmp-list-'+side);
  if (!el) return [];
  var out = [];
  el.querySelectorAll('.drag-card').forEach(function(card) {
    try { out.push(JSON.parse((card.dataset.player||'').replace(/&quot;/g,'"'))); } catch(e){}
  });
  return out;
}

function pm_build() {
  var mine = pm_getPlayers('mine'), opp = pm_getPlayers('opp');
  if (!mine.length || !opp.length) return '<p style="color:var(--text2);padding:12px">Roster data not yet loaded.</p>';

  var POS = ['C','1B','2B','3B','SS','OF','UTIL','P'];
  function bucket(p) { return p.isp ? 'P' : (p.pos || 'UTIL'); }
  function sortBase(arr) { return arr.slice().sort(function(a,b){return parseFloat(b.base)-parseFloat(a.base);}); }

  var myB={}, opB={};
  mine.forEach(function(p){ var b=bucket(p); if(!myB[b])myB[b]=[]; myB[b].push(p); });
  opp.forEach(function(p){ var b=bucket(p); if(!opB[b])opB[b]=[]; opB[b].push(p); });

  function pCard(p, flip) {
    if (!p) return '<div class="pmatch-empty">\u2014</div>';
    var base = parseFloat(p.base)||0;
    var inj = p.status && p.status!=='ACTIVE'
      ? '<span class="lv-inj-badge" style="font-size:9px">'+p.status.replace(/_/g,' ')+'</span>' : '';
    return '<div class="pmatch-player">'
      +(flip?'<div class="pmatch-score pmatch-score-opp">'+base.toFixed(0)+'</div>':'')
      +'<div class="pmatch-av"><img src="'+p.hs+'" alt="'+p.name+'" class="lv-av-img" style="width:38px;height:38px" onerror="this.style.display=\'none\'"></div>'
      +'<div class="pmatch-info" style="text-align:'+(flip?'right':'left')+'">'
      +'<div class="pmatch-name">'+p.name+inj+'</div>'
      +'<div class="pmatch-sub">'+p.mlb+' \u00b7 Proj\u00a0'+parseInt(p.proj||0)+'</div>'
      +'</div>'
      +(!flip?'<div class="pmatch-score">'+base.toFixed(0)+'</div>':'')
      +'</div>';
  }

  // Scorecard
  var mW=0, oW=0, ties=0;
  POS.forEach(function(pos){
    var m=sortBase(myB[pos]||[])[0], o=sortBase(opB[pos]||[])[0];
    if(!m&&!o) return;
    var mb=m?parseFloat(m.base):0, ob=o?parseFloat(o.base):0;
    if(mb>ob) mW++; else if(ob>mb) oW++; else ties++;
  });

  var tot = mW+oW+ties||1;
  var pct = (mW/tot*100).toFixed(0);

  var html = '<div class="pmatch-summary">'
    +'<div class="pmatch-sum-side pmatch-sum-mine"><div class="pmatch-sum-num">'+mW+'</div><div class="pmatch-sum-lbl">positions won</div></div>'
    +'<div class="pmatch-sum-center">'
    +'<div class="pmatch-sum-track"><div class="pmatch-sum-fill" style="width:'+pct+'%"></div></div>'
    +'<div class="pmatch-sum-ties">'+ties+' tied</div>'
    +'</div>'
    +'<div class="pmatch-sum-side pmatch-sum-opp"><div class="pmatch-sum-num">'+oW+'</div><div class="pmatch-sum-lbl">positions won</div></div>'
    +'</div>';

  html += '<div class="pmatch-col-labels">'
    +'<span style="color:#22c55e;font-weight:700">\uD83D\uDFE2 Your Team</span>'
    +'<span style="color:var(--text2);font-weight:700">POS</span>'
    +'<span style="color:#f59e0b;font-weight:700">Opponent \uD83D\uDFE1</span>'
    +'</div>';

  var SHOW = {C:1,'1B':1,'2B':1,'3B':1,SS:1,OF:3,UTIL:1,P:4};
  POS.forEach(function(pos){
    var ms=sortBase(myB[pos]||[]), os=sortBase(opB[pos]||[]);
    var maxShow = SHOW[pos]||1;
    var rows = Math.min(Math.max(ms.length,os.length), maxShow);
    if(!rows) return;
    for(var i=0;i<rows;i++){
      var m=ms[i]||null, o=os[i]||null;
      var mb=m?parseFloat(m.base):0, ob=o?parseFloat(o.base):0;
      var mWin=mb>ob+0.1, oWin=ob>mb+0.1;
      html += '<div class="pmatch-row'+(mWin?' pmatch-mine-wins':oWin?' pmatch-opp-wins':'')+'">'
        +'<div class="pmatch-side pmatch-left'+(mWin?' pmatch-winner':'')+'">'+pCard(m,false)+'</div>'
        +'<div class="pmatch-badge-col">'
        +'<span class="pos pos-'+pos.toLowerCase()+'">'+pos+'</span>'
        +(mWin?'<div class="pmatch-arrow pmatch-arrow-l">\u25C4 edge</div>'
               :oWin?'<div class="pmatch-arrow pmatch-arrow-r">edge \u25BA</div>'
                    :'<div class="pmatch-arrow pmatch-arrow-t">\u2248 even</div>')
        +'</div>'
        +'<div class="pmatch-side pmatch-right'+(oWin?' pmatch-winner':'')+'">'+pCard(o,true)+'</div>'
        +'</div>';
    }
  });

  return html;
}

var _pmBuilt = false;
function pm_lazyBuild() {
  if (_pmBuilt) return;
  _pmBuilt = true;
  var el = document.getElementById('pmatch-content');
  if (el) el.innerHTML = pm_build();
}

// ─── Inject UI elements on DOM load ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {

  // ── 1. Lineup View toggle in My Team ────────────────────────────────────────
  var myPane = document.querySelector('.team-viewer-pane[data-display-name="My Team"]')
             || document.querySelector('.team-viewer-pane');
  if (myPane) {
    var rcCard = null;
    var cards = myPane.querySelectorAll('.card');
    for (var ci=0; ci<cards.length; ci++) {
      if (cards[ci].querySelector('.rc-grid')) { rcCard = cards[ci]; break; }
    }
    if (rcCard) {
      rcCard.id = 'lv-roster-section';
      var lvDiv = document.createElement('div');
      lvDiv.id = 'lv-lineup-section';
      lvDiv.style.display = 'none';
      rcCard.parentNode.insertBefore(lvDiv, rcCard.nextSibling);

      var secHead = rcCard.querySelector('.sec-head');
      if (secHead) {
        var btn = document.createElement('button');
        btn.id = 'lv-toggle-btn';
        btn.className = 'lv-toggle-btn';
        btn.textContent = '\uD83D\uDCC5 Lineup View';
        btn.onclick = toggleLineupView;
        secHead.appendChild(btn);
      }
    }
  }

  // ── 2. Position Matchup section in Compare Players tab ─────────────────────
  var cmpCard = document.querySelector('#ipane-compare .card');
  if (cmpCard) {
    var pmSec = document.createElement('div');
    pmSec.id = 'pm-outer';
    pmSec.innerHTML = '<div class="pmatch-header-row">'
      +'<h4 class="mc-section-title" style="margin:0">\u2694\uFE0F Position Matchups</h4>'
      +'<p style="color:var(--text2);font-size:.82rem;margin:.35rem 0 1rem">FDB model score head-to-head at every position. Green = your edge. Click a player to open deep compare.</p>'
      +'</div>'
      +'<div id="pmatch-content" style="margin-bottom:1.5rem"></div>';
    cmpCard.insertBefore(pmSec, cmpCard.querySelector('.cmp-layout'));
  }

  // Rebuild if Compare tab is already visible
  if (document.getElementById('ipane-compare') &&
      document.getElementById('ipane-compare').classList.contains('visible')) {
    pm_lazyBuild();
  }
});

// Patch switchInnerTab to lazy-build position matchup on first open
(function(){
  var _orig = window.switchInnerTab;
  if (typeof _orig === 'function') {
    window.switchInnerTab = function(tab) {
      _orig(tab);
      if (tab === 'compare') pm_lazyBuild();
    };
  }
})();

/* ══════════════════════════════════════════ UNIVERSAL PLAYER CLICK SYSTEM */

// Global player registry: name → full data object
var PLAYER_REGISTRY = {};

function _buildPlayerRegistry() {
  // 1. Pull from every .rc card (has full data-* attributes)
  document.querySelectorAll('.rc[data-name]').forEach(function(card) {
    var d = card.dataset;
    var adv = {};
    try { adv = JSON.parse((d.adv || '{}').replace(/&quot;/g, '"')); } catch(e) {}
    var name = d.name || '';
    if (!name) return;
    PLAYER_REGISTRY[name] = {
      name:      name,
      mlbam:     d.mlbam  || '',
      isp:       d.pitcher === 'true',
      pos:       d.pos    || '',
      team:      d.team   || '',
      base:      d.base   || '0',
      fit:       d.fit    || '0',
      proj:      d.proj   || '0',
      hs:        d.hs     || '',
      hs2:       d.hs2    || '',
      ini:       d.ini    || (name.split(' ').map(function(w){return w[0];}).join('')),
      injStatus: d.injStatus || 'ACTIVE',
      onIl:      d.onIl   === 'true',
      adv:       adv,
      _el:       card
    };
  });

  // 2. Supplement from FDB_ROSTER (has mlbam IDs)
  if (window.FDB_ROSTER) {
    FDB_ROSTER.forEach(function(p) {
      if (p.mlbam && PLAYER_REGISTRY[p.name]) {
        PLAYER_REGISTRY[p.name].mlbam = p.mlbam;
      }
    });
  }

  // 3. Pull from drag-cards (matchup compare lists)
  document.querySelectorAll('.drag-card[data-player]').forEach(function(card) {
    try {
      var p = JSON.parse((card.dataset.player || '').replace(/&quot;/g, '"'));
      if (p.name && !PLAYER_REGISTRY[p.name]) {
        PLAYER_REGISTRY[p.name] = {
          name:      p.name,
          mlbam:     p.mlbam || '',
          isp:       !!p.isp,
          pos:       p.pos   || '',
          team:      p.mlb   || '',
          base:      p.base  || '0',
          fit:       p.fit   || '0',
          proj:      p.proj  || '0',
          hs:        p.hs    || '',
          hs2:       p.hs2   || '',
          ini:       p.ini   || '',
          injStatus: p.status || 'ACTIVE',
          onIl:      false,
          adv:       {},
          _el:       card
        };
      }
    } catch(e) {}
  });
}

// Open player modal from registry data (no event/element needed)
function openPlayerByName(name) {
  var p = PLAYER_REGISTRY[name];
  if (!p) {
    // Try fuzzy match (last name)
    var lname = name.split(' ').pop().toLowerCase();
    Object.keys(PLAYER_REGISTRY).forEach(function(key) {
      if (key.toLowerCase().indexOf(lname) >= 0) p = PLAYER_REGISTRY[key];
    });
  }
  if (!p) return;

  // Build a synthetic element with dataset attrs for the original openPlayerModal
  var fake = document.createElement('div');
  fake.dataset.name      = p.name;
  fake.dataset.mlbam     = p.mlbam;
  fake.dataset.pitcher   = p.isp ? 'true' : 'false';
  fake.dataset.pos       = p.pos;
  fake.dataset.team      = p.team;
  fake.dataset.base      = p.base;
  fake.dataset.fit       = p.fit;
  fake.dataset.proj      = p.proj;
  fake.dataset.hs        = p.hs;
  fake.dataset.hs2       = p.hs2;
  fake.dataset.ini       = p.ini;
  fake.dataset.injStatus = p.injStatus;
  fake.dataset.onIl      = p.onIl ? 'true' : 'false';
  fake.dataset.adv       = JSON.stringify(p.adv);

  // Dispatch a synthetic event with stopPropagation stub
  var fakeEv = { stopPropagation: function() {} };
  openPlayerModal(fakeEv, fake);
}

// Make an element a clickable player link
function _makePlayerLink(el, name) {
  if (el.dataset.playerLinked) return;
  el.dataset.playerLinked = '1';
  el.style.cursor = 'pointer';
  el.title = 'View ' + name + ' stats & analytics';
  el.addEventListener('click', function(e) {
    e.stopPropagation();
    openPlayerByName(name);
  });
}

// Scan the whole page and wire up every player name
function _wireAllPlayerNames() {
  // Pattern: anything with a text node matching a registry name
  // We target specific known class names across all sections

  var selectors = [
    // Roster cards
    '.rc-name',
    // Lineup view
    '.lv-row-name',
    // Drag cards in matchup
    '.drag-card-name',
    // News tab
    '.news-name',
    // Position matchup (pmatch-name)
    '.pmatch-name',
    // League / schedule chips
    '.sched-chip-name',
    // Draft room (dr-cell-name)
    '.dr-cell-name',
    // Draft roster table (dr-roster-name)
    '.dr-roster-name',
    // Waiver list
    '.wv-name',
    // Waiver player cards
    '.pc-name',
  ];

  selectors.forEach(function(sel) {
    document.querySelectorAll(sel).forEach(function(el) {
      var name = el.textContent.trim();
      // Strip any badge text (injury suffixes)
      name = name.split('\n')[0].trim();
      if (PLAYER_REGISTRY[name]) {
        _makePlayerLink(el, name);
      } else {
        // Try partial match
        var key = Object.keys(PLAYER_REGISTRY).find(function(k) {
          return k.startsWith(name) || name.startsWith(k.split(' ')[1] || k);
        });
        if (key) _makePlayerLink(el, key);
      }
    });
  });

  // Also wire inline player name spans/divs that have data-player-name attr
  document.querySelectorAll('[data-player-name]').forEach(function(el) {
    var name = el.dataset.playerName;
    if (name) _makePlayerLink(el, name);
  });
}

// Run on page load + re-run when tabs switch (new content may load)
document.addEventListener('DOMContentLoaded', function() {
  _buildPlayerRegistry();
  _wireAllPlayerNames();
});

// (switchTab re-wiring now built into consolidated switchTab above)

// Also re-wire after lineup view toggles and position matchup builds
var _origToggleLV = window.toggleLineupView;
if (typeof _origToggleLV === 'function') {
  window.toggleLineupView = function() {
    _origToggleLV();
    setTimeout(_wireAllPlayerNames, 200);
  };
}

var _origPmLazy = window.pm_lazyBuild;
if (typeof _origPmLazy === 'function') {
  window.pm_lazyBuild = function() {
    _origPmLazy();
    setTimeout(_wireAllPlayerNames, 300);
  };
}

/* ═══════════════════════════════════════════════════════════
   TRADE CALCULATOR  (B+C Hybrid)
═══════════════════════════════════════════════════════════ */
var TC = {
  teams: {},        // {teamName: [{name,pos,base,fit,proj,adv,hs,mlbam,isp,tier,sig,statLabel,statVal},...]}
  teamOrder: [],    // ordered list of team names
  myTeam: '',
  basketA: [],      // players from team A in trade
  basketB: [],      // players from team B in trade
  teamA: '',
  teamB: '',
  filterA: 'all',   // 'all' | 'H' | 'P'
  filterB: 'all',
  searchA: '',
  searchB: '',
  built: false
};

/* ── Extract all teams from DOM ─────────────────────────── */
function tc_extractTeams() {
  TC.teams = {};
  TC.teamOrder = [];
  document.querySelectorAll('.team-viewer-pane').forEach(function(pane) {
    var tname = (pane.dataset.team || '').trim();
    if (!tname) return;
    TC.teamOrder.push(tname);
    TC.teams[tname] = [];
    pane.querySelectorAll('.rc[data-name]').forEach(function(rc) {
      var base = parseFloat(rc.dataset.base) || 0;
      var fit  = parseFloat(rc.dataset.fit)  || 0;
      var proj = parseFloat(rc.dataset.proj) || 0;
      var adv  = {};
      try { adv = JSON.parse(rc.dataset.adv || '{}'); } catch(e) {}
      var tier = base >= 75 ? 'unt' : base >= 35 ? 'get' : 'avl';
      var isp  = rc.dataset.pitcher === 'true';
      // Derive one key stat + signal badge from adv
      var statLabel = '', statVal = '', sig = '', sigCls = '';
      if (isp) {
        if (adv.siera) { statLabel='SIERA'; statVal=parseFloat(adv.siera).toFixed(2); }
        else if (adv.fip) { statLabel='FIP'; statVal=parseFloat(adv.fip).toFixed(2); }
        if (adv.velocity_alert) {
          if (String(adv.velocity_alert).toLowerCase().indexOf('buy')!==-1||String(adv.velocity_alert).toLowerCase().indexOf('sell')!==-1) {
            if (String(adv.velocity_alert).toLowerCase().indexOf('buy')!==-1) { sig='BUY'; sigCls='buy'; }
            else { sig='SELL'; sigCls='sell'; }
          }
        }
      } else {
        if (adv.wrc_plus) { statLabel='wRC+'; statVal=String(Math.round(adv.wrc_plus)); }
        else if (adv.xwoba) { statLabel='xwOBA'; statVal=parseFloat(adv.xwoba).toFixed(3); }
        if (adv.statcast_alert) {
          if (String(adv.statcast_alert).toLowerCase().indexOf('breakout')!==-1) { sig='BRKOUT'; sigCls='brk'; }
          else if (String(adv.statcast_alert).toLowerCase().indexOf('regress')!==-1) { sig='REGRESS'; sigCls='reg'; }
        }
      }
      TC.teams[tname].push({
        name: rc.dataset.name || '',
        pos:  rc.dataset.pos  || '',
        team: rc.dataset.team2 || rc.dataset.team || '',
        base: base, fit: fit, proj: proj, adv: adv,
        hs:   rc.dataset.hs || '', mlbam: rc.dataset.mlbam || '',
        isp:  isp,
        inj:  rc.dataset.injStatus || 'ACTIVE',
        onIL: rc.dataset.onIl === 'true',
        tier: tier,
        statLabel: statLabel, statVal: statVal,
        sig: sig, sigCls: sigCls
      });
    });
    TC.teams[tname].sort(function(a,b){ return b.base - a.base; });
  });

  // Identify My Team — first pane marked my-team, else first in order
  var myPane = document.querySelector('.team-viewer-pane[data-my-team="true"]');
  if (!myPane) myPane = document.querySelector('.team-viewer-pane');
  TC.myTeam = myPane ? (myPane.dataset.team || TC.teamOrder[0] || '') : (TC.teamOrder[0] || '');
}

/* ── Tier helpers ───────────────────────────────────────── */
function tc_tierLabel(t) {
  if (t==='unt') return '🔴 Untouchable';
  if (t==='get') return '🟡 Gettable';
  return '🟢 Available';
}

/* ── Build a roster table column (side = 'a' | 'b') ─────── */
function tc_buildTable(side, teamName) {
  var allPlayers = TC.teams[teamName] || [];
  var filter = side === 'a' ? TC.filterA : TC.filterB;
  var search = (side === 'a' ? TC.searchA : TC.searchB).toLowerCase();
  var totalBase = allPlayers.reduce(function(s,p){return s+p.base;},0);

  // Header
  var sideColor = side === 'a' ? '#58a6ff' : '#f97316';
  var html = '<div class="tc-tbl-head ' + side + '">';
  html += '<div><div class="tc-tbl-team">' + _esc(teamName) + '</div>';
  html += '<div class="tc-tbl-meta">' + allPlayers.length + ' players &nbsp;·&nbsp; drag or click + to add</div></div>';
  html += '<div class="tc-tbl-total ' + side + '">Σ ' + totalBase.toFixed(0) + '</div>';
  html += '</div>';

  // Controls
  html += '<div class="tc-tbl-ctrl">';
  html += '<input class="tc-tbl-search" type="text" placeholder="🔍 Search…" value="' + _esc(search) + '"'
    + ' oninput="tc_onSearch(\'' + side + '\',this.value)">';
  html += '<button class="tc-fpill' + (filter==='all'?' active':'') + '" onclick="tc_setFilter(\'' + side + '\',\'all\')">All</button>';
  html += '<button class="tc-fpill' + (filter==='H'?' active':'') + '" onclick="tc_setFilter(\'' + side + '\',\'H\')">H</button>';
  html += '<button class="tc-fpill' + (filter==='P'?' active':'') + '" onclick="tc_setFilter(\'' + side + '\',\'P\')">P</button>';
  html += '</div>';

  // Player list
  html += '<div class="tc-tbl-scroll">';

  var tiers = ['unt','get','avl'];
  tiers.forEach(function(tier) {
    var group = allPlayers.filter(function(p) {
      if (p.tier !== tier) return false;
      if (filter === 'H' && p.isp) return false;
      if (filter === 'P' && !p.isp) return false;
      if (search && p.name.toLowerCase().indexOf(search) === -1) return false;
      return true;
    });
    if (!group.length) return;

    // Tier separator
    html += '<div class="tc-tier-sep ' + tier + '">';
    html += '<div class="tc-tier-sep-dot ' + tier + '"></div>';
    html += tc_tierLabel(tier) + ' <span style="color:var(--text3);margin-left:4px;font-weight:400">(' + group.length + ')</span>';
    html += '</div>';

    group.forEach(function(p) {
      var inA = TC.basketA.some(function(x){return x.name===p.name;});
      var inB = TC.basketB.some(function(x){return x.name===p.name;});
      var inTrade = inA || inB;
      var posFirst = (p.pos||'').split(',')[0].trim();
      var posType  = p.isp ? 'sp' : 'h';
      if (posFirst==='RP'||posFirst==='CL') posType='rp';

      // Avatar
      var avHtml = p.hs
        ? '<img class="tc-av" src="' + _esc(p.hs) + '" onerror="this.onerror=null;this.outerHTML=\'<div class=&quot;tc-av-fb&quot;>' + _esc(p.name.substring(0,2).toUpperCase()) + '</div>\'">'
        : '<div class="tc-av-fb">' + _esc(p.name.substring(0,2).toUpperCase()) + '</div>';

      var rowCls = 'tc-player tc-tier-' + tier + (inA?' tc-in-trade':'') + (inB?' tc-in-trade-b':'');
      var btnCls = inA ? 'tc-add-btn in-a' : (inB ? 'tc-add-btn in-b' : 'tc-add-btn');
      var btnTxt = (inA||inB) ? '✓' : '+';

      html += '<div class="' + rowCls + '"'
        + ' draggable="true"'
        + ' data-name="' + _esc(p.name) + '"'
        + ' data-side="' + side + '"'
        + ' ondragstart="tc_onDragStart(event,\'' + side + '\',\'' + _escQ(p.name) + '\')"'
        + '>';
      html += avHtml;
      html += '<div class="tc-info">';
      html += '<div class="tc-pname" data-player-linked onclick="openPlayerByName(\'' + _escQ(p.name) + '\')">' + _esc(p.name) + '</div>';
      html += '<div class="tc-psub">';
      html += '<span class="tc-pos-tag ' + posType + '">' + _esc(posFirst) + '</span>';
      html += '<span style="color:var(--text3)">' + _esc(p.team||'') + '</span>';
      if (p.statLabel) {
        html += '<span class="tc-stat-pill">' + _esc(p.statLabel) + ' ' + _esc(p.statVal) + '</span>';
      }
      if (p.sig) {
        html += '<span class="tc-sig-badge ' + p.sigCls + '">' + _esc(p.sig) + '</span>';
      }
      html += '</div></div>';
      html += '<div class="tc-score-cell">' + p.base.toFixed(0) + '</div>';
      html += '<button class="' + btnCls + '"'
        + (inTrade ? ' disabled' : ' onclick="tc_addToBasket(\'' + side + '\',\'' + _escQ(p.name) + '\')"')
        + '>' + btnTxt + '</button>';
      html += '</div>';
    });
  });

  html += '</div>'; // tc-tbl-scroll
  return html;
}

/* ── Build the basket bar (full-width) ──────────────────── */
function tc_buildBbar() {
  var aVal = TC.basketA.reduce(function(s,p){return s+p.base;},0);
  var bVal = TC.basketB.reduce(function(s,p){return s+p.base;},0);
  var diff = aVal - bVal; // + means A sending more (A loses value)

  // Chip list helper
  function chips(basket, side) {
    if (!basket.length) return '<div class="tc-bzone-empty">Drop players here or click + above</div>';
    return basket.map(function(p) {
      var posFirst = (p.pos||'').split(',')[0].trim();
      return '<span class="tc-bchip ' + side + '">'
        + _esc(p.name) + ' <span class="tc-bchip-pts">' + p.base.toFixed(0) + '</span>'
        + '<button class="tc-bchip-rm" onclick="tc_removeFromBasket(\'' + side + '\',\'' + _escQ(p.name) + '\')">✕</button>'
        + '</span>';
    }).join('');
  }

  // Value diff badge
  var diffCls = 'neu', diffTxt = '— Even';
  if (Math.abs(diff) > 3) {
    if (diff > 0) { diffCls='neg'; diffTxt='A −' + diff.toFixed(0) + ' pts'; }
    else          { diffCls='pos'; diffTxt='A +' + Math.abs(diff).toFixed(0) + ' pts'; }
  }

  var evalDis = (!TC.basketA.length && !TC.basketB.length) ? ' disabled' : '';
  var html = '';
  html += '<div class="tc-bbar-head">';
  html += '<div class="tc-bbar-title">🧺 Trade Baskets</div>';
  html += '<div class="tc-bbar-hint">Drag from rosters above, or click +</div>';
  html += '</div>';
  html += '<div class="tc-bbar-body">';

  // Zone A
  html += '<div class="tc-bzone a" ondragover="tc_onDragOver(event)" ondrop="tc_onDrop(event,\'a\')" ondragleave="tc_onDragLeave(event)">';
  html += '<div class="tc-bzone-lbl"><span>📤 ' + _esc(TC.teamA.substring(0,20)) + ' Sends</span>';
  html += '<span class="tc-bzone-lbl-total">' + (aVal > 0 ? aVal.toFixed(0) + ' pts' : '') + '</span></div>';
  html += '<div class="tc-bzone-chips">' + chips(TC.basketA, 'a') + '</div>';
  html += '</div>';

  // Center exchange
  html += '<div class="tc-exchg">';
  html += '<div class="tc-exchg-icon">⇄</div>';
  html += '<div class="tc-exchg-diff ' + diffCls + '">' + diffTxt + '</div>';
  html += '</div>';

  // Zone B
  html += '<div class="tc-bzone b" ondragover="tc_onDragOver(event)" ondrop="tc_onDrop(event,\'b\')" ondragleave="tc_onDragLeave(event)">';
  html += '<div class="tc-bzone-lbl"><span>📤 ' + _esc(TC.teamB.substring(0,20)) + ' Sends</span>';
  html += '<span class="tc-bzone-lbl-total">' + (bVal > 0 ? bVal.toFixed(0) + ' pts' : '') + '</span></div>';
  html += '<div class="tc-bzone-chips">' + chips(TC.basketB, 'b') + '</div>';
  html += '</div>';

  html += '</div>'; // tc-bbar-body
  html += '<div class="tc-bbar-footer">';
  html += '<button id="tc-eval-btn" class="tc-analyze-btn"' + evalDis + ' onclick="tc_analyzeTrade()">⚡ Analyze Trade</button>';
  html += '<button class="tc-clear-btn" onclick="tc_clearBaskets()">✕ Clear All</button>';
  html += '</div>';
  return html;
}

/* ── Drag & drop handlers ───────────────────────────────── */
var _tcDragPlayer = null;
var _tcDragSide   = null;

function tc_onDragStart(e, side, playerName) {
  _tcDragPlayer = playerName;
  _tcDragSide   = side;
  e.dataTransfer.effectAllowed = 'move';
  var el = e.currentTarget;
  setTimeout(function(){ if(el) el.classList.add('tc-dragging'); }, 0);
}

function tc_onDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  e.currentTarget.classList.add('tc-drag-over');
}

function tc_onDragLeave(e) {
  e.currentTarget.classList.remove('tc-drag-over');
}

function tc_onDrop(e, targetSide) {
  e.preventDefault();
  e.currentTarget.classList.remove('tc-drag-over');
  if (!_tcDragPlayer) return;

  // Look up player in source team
  var sourceTeam = _tcDragSide === 'a' ? TC.teamA : TC.teamB;
  var players = TC.teams[sourceTeam] || [];
  var p = players.find(function(x){ return x.name === _tcDragPlayer; });
  if (!p) { _tcDragPlayer = null; return; }

  // Prevent duplicates across both baskets
  var inA = TC.basketA.some(function(x){return x.name===p.name;});
  var inB = TC.basketB.some(function(x){return x.name===p.name;});
  if (inA || inB) { _tcDragPlayer = null; return; }

  if (targetSide === 'a') TC.basketA.push(p);
  else TC.basketB.push(p);

  _tcDragPlayer = null;
  tc_render();
}

/* ── Click-to-add handler ───────────────────────────────── */
function tc_addToBasket(side, playerName) {
  var teamName = side === 'a' ? TC.teamA : TC.teamB;
  var players = TC.teams[teamName] || [];
  var p = players.find(function(x){ return x.name === playerName; });
  if (!p) return;
  var inA = TC.basketA.some(function(x){return x.name===p.name;});
  var inB = TC.basketB.some(function(x){return x.name===p.name;});
  if (inA || inB) return;
  if (side === 'a') TC.basketA.push(p);
  else TC.basketB.push(p);
  tc_render();
}

/* ── Remove from basket ─────────────────────────────────── */
function tc_removeFromBasket(side, playerName) {
  if (side === 'a') TC.basketA = TC.basketA.filter(function(p){ return p.name !== playerName; });
  else TC.basketB = TC.basketB.filter(function(p){ return p.name !== playerName; });
  tc_render();
}

function tc_clearBaskets() {
  TC.basketA = [];
  TC.basketB = [];
  var res = document.getElementById('tc-result');
  if (res) { res.innerHTML = ''; res.style.display = 'none'; }
  tc_render();
}

/* ── Search / filter handlers ───────────────────────────── */
function tc_setFilter(side, val) {
  if (side === 'a') TC.filterA = val;
  else TC.filterB = val;
  tc_renderTable(side);
}

function tc_onSearch(side, val) {
  if (side === 'a') TC.searchA = val;
  else TC.searchB = val;
  tc_renderTable(side);
}

/* ── Re-render one table ────────────────────────────────── */
function tc_renderTable(side) {
  var teamName = side === 'a' ? TC.teamA : TC.teamB;
  var el = document.getElementById('tc-tbl-' + side);
  if (el) el.innerHTML = tc_buildTable(side, teamName);
}

/* ── Re-render baskets + eval button ────────────────────── */
function tc_renderBbar() {
  var el = document.getElementById('tc-bbar-inner');
  if (el) el.innerHTML = tc_buildBbar();
}

/* ── Full re-render ─────────────────────────────────────── */
function tc_render() {
  tc_renderTable('a');
  tc_renderTable('b');
  tc_renderBbar();
}

/* ── Team selectors changed ─────────────────────────────── */
function tc_onTeamAChange(val) {
  TC.teamA = val;
  TC.basketA = [];
  TC.searchA = '';
  TC.filterA = 'all';
  var res = document.getElementById('tc-result');
  if (res) { res.innerHTML = ''; res.style.display = 'none'; }
  tc_render();
}
function tc_onTeamBChange(val) {
  TC.teamB = val;
  TC.basketB = [];
  TC.searchB = '';
  TC.filterB = 'all';
  var res = document.getElementById('tc-result');
  if (res) { res.innerHTML = ''; res.style.display = 'none'; }
  tc_render();
}

/* ── Analyze trade ──────────────────────────────────────── */
function tc_analyzeTrade() {
  if (!TC.basketA.length && !TC.basketB.length) return;

  var aOut = TC.basketA;   // Team A sends
  var bOut = TC.basketB;   // Team B sends (Team A receives)

  var aOutVal = aOut.reduce(function(s,p){return s+p.base;},0);
  var bOutVal = bOut.reduce(function(s,p){return s+p.base;},0);
  var aDelta  = bOutVal - aOutVal;  // + means Team A gains value

  var aInFit   = bOut.reduce(function(s,p){return s+p.fit;},0) / (bOut.length||1);
  var aOutFit  = aOut.reduce(function(s,p){return s+p.fit;},0) / (aOut.length||1);
  var aFitDelta = (bOut.length?aInFit:0) - (aOut.length?aOutFit:0);

  var aProjDelta = bOut.reduce(function(s,p){return s+p.proj;},0)
                - aOut.reduce(function(s,p){return s+p.proj;},0);

  var score = aDelta*0.5 + aProjDelta*0.3 + aFitDelta*0.2;
  var verdictCls, verdictLbl, verdictDetail;
  if (score > 4) {
    verdictCls='win'; verdictLbl='✅ Team A Wins This Trade';
    verdictDetail = _esc(TC.teamA) + ' gains value in this deal.';
  } else if (score < -4) {
    verdictCls='loss'; verdictLbl='❌ Team A Loses Value';
    verdictDetail = _esc(TC.teamA) + ' gives up more than it receives.';
  } else {
    verdictCls='even'; verdictLbl='⚖️ Roughly Even Trade';
    verdictDetail = 'Both sides receive similar value.';
  }

  var aBaseAfter = (TC.teams[TC.teamA]||[]).reduce(function(s,p){return s+p.base;},0) - aOutVal + bOutVal;
  var bBaseAfter = (TC.teams[TC.teamB]||[]).reduce(function(s,p){return s+p.base;},0) - bOutVal + aOutVal;

  // Build insights
  var insights = [];
  if (Math.abs(aDelta) > 10) {
    var winner = aDelta>0 ? TC.teamA : TC.teamB;
    insights.push({icon:'💡', text:'Value gap of <strong>' + Math.abs(aDelta).toFixed(1) + ' pts</strong> — ' + _esc(winner) + ' gets the better end on raw FDB value.'});
  }
  var untOut = aOut.filter(function(p){return p.tier==='unt';}).length;
  if (untOut) insights.push({icon:'🔴', text:_esc(TC.teamA)+' sends <strong>'+untOut+' Untouchable player'+(untOut>1?'s':'')+' away</strong> — ensure return value is elite.'});
  var untIn = bOut.filter(function(p){return p.tier==='unt';}).length;
  if (untIn) insights.push({icon:'🌟', text:_esc(TC.teamA)+' acquires <strong>'+untIn+' elite player'+(untIn>1?'s':'')+' </strong> — strong haul.'});
  if (Math.abs(aFitDelta) > 5) {
    insights.push({icon:'🎯', text:'Team fit for '+_esc(TC.teamA)+' <strong>'+(aFitDelta>0?'improves':'decreases')+' by '+Math.abs(aFitDelta).toFixed(1)+' pts</strong>.'});
  }
  var ilOut = aOut.filter(function(p){return p.onIL;}).length;
  if (ilOut) insights.push({icon:'⚠️', text:'<strong>'+ilOut+' player'+(ilOut>1?'s':'')+' being sent</strong> are on the IL — selling injured assets carries risk.'});
  var pIn  = bOut.filter(function(p){return p.isp;}).length;
  var pOut = aOut.filter(function(p){return p.isp;}).length;
  if (pIn!==pOut) {
    var pd=Math.abs(pIn-pOut);
    insights.push({icon:'⚾', text:_esc(TC.teamA)+' will <strong>'+(pIn>pOut?'add':'lose')+' '+pd+' pitcher'+(pd>1?'s':'')+' </strong> — review rotation/bullpen balance.'});
  }
  var regOuts = aOut.filter(function(p){return p.sigCls==='reg'||p.sigCls==='sell';}).length;
  if (regOuts) insights.push({icon:'📉', text:'<strong>'+regOuts+' outgoing player'+(regOuts>1?'s':'')+' flagged REGRESS/SELL</strong> — good time to move them.'});
  var brkIn = bOut.filter(function(p){return p.sigCls==='brk'||p.sigCls==='buy';}).length;
  if (brkIn) insights.push({icon:'🟢', text:'<strong>'+brkIn+' incoming player'+(brkIn>1?'s':'')+' flagged BREAKOUT/BUY-LOW</strong> — potentially buying low here.'});
  if (!insights.length) insights.push({icon:'✅', text:'Trade looks balanced — no major red flags or edges detected.'});
  // Cap at 3 for clean grid
  if (insights.length > 3) insights = insights.slice(0, 3);

  // Render
  var sign = function(n){ return n>=0?'+':''; };

  var html = '';

  // Top: verdict + 5 metrics
  html += '<div class="tc-result-top">';
  html += '<div class="tc-verdict-col ' + verdictCls + '">';
  html += '<div class="tc-verdict-title">Trade Analysis</div>';
  html += '<div class="tc-verdict-lbl ' + verdictCls + '">' + verdictLbl + '</div>';
  html += '<div class="tc-verdict-detail">' + verdictDetail + '</div>';

  // P6: Add positional gap warnings
  var myRosterTeam = TC.teams[TC.teamA] || [];
  var gapWarnings = tc_getPositionalGaps(aOut, myRosterTeam);
  var gapHtml = tc_renderGapWarnings(gapWarnings);
  if (gapHtml) {
    html += gapHtml;
  }

  // P6: Add ROS context for key players
  var weeksRemaining = 26 - Math.ceil((Date.now() - new Date(2026, 2, 30).getTime()) / (7 * 24 * 60 * 60 * 1000));
  if (weeksRemaining < 0) weeksRemaining = 0;
  aOut.forEach(function(p) {
    var pills = tc_rosContext(p, weeksRemaining);
    var rosPillHtml = tc_renderRosPills(pills);
    if (rosPillHtml && p.tier === 'unt') {
      html += '<div style="margin-top:4px"><small style="color:var(--text3)">Sending: ' + _esc(p.name) + '</small>' + rosPillHtml + '</div>';
    }
  });

  html += '</div>';
  html += '<div class="tc-metrics-band">';
  html += tc_metricCell(sign(aDelta)+aDelta.toFixed(1), aDelta, 'Value Delta', 'FDB base pts');
  html += tc_metricCell(sign(aProjDelta)+aProjDelta.toFixed(0), aProjDelta, 'Proj Pts Δ', 'season projection');
  html += tc_metricCell(sign(aFitDelta)+aFitDelta.toFixed(1), aFitDelta, 'Fit Δ', 'roster fit score');
  html += tc_metricCell(aOut.length + '→' + bOut.length, 0, 'Assets', 'A sends → B sends', true);
  html += tc_metricCell(aBaseAfter.toFixed(0), aDelta, 'A Total', 'after trade', true);
  html += '</div>';
  html += '</div>'; // tc-result-top

  // Post-trade rosters
  html += '<div class="tc-post-grid">';
  html += tc_postCol(TC.teamA, TC.basketA, TC.basketB, aBaseAfter);
  html += tc_postCol(TC.teamB, TC.basketB, TC.basketA, bBaseAfter);
  html += '</div>';

  // 3-col insights grid
  html += '<div class="tc-insights-grid">';
  insights.forEach(function(ins) {
    html += '<div class="tc-insight-card"><span class="tc-insight-icon">' + ins.icon + '</span>';
    html += '<span class="tc-insight-text">' + ins.text + '</span></div>';
  });
  html += '</div>';

  var resEl = document.getElementById('tc-result');
  if (resEl) {
    resEl.innerHTML = html;
    resEl.style.display = '';
    setTimeout(function(){ resEl.scrollIntoView({behavior:'smooth',block:'nearest'}); }, 100);
  }
}

function tc_metricCell(val, delta, lbl, hint, neutral) {
  var cls = neutral ? 'neu' : (delta > 0 ? 'pos' : delta < 0 ? 'neg' : 'neu');
  return '<div class="tc-metric-cell">'
    + '<div class="tc-metric-val ' + cls + '">' + val + '</div>'
    + '<div class="tc-metric-lbl">' + lbl + '</div>'
    + '<div class="tc-metric-hint">' + hint + '</div>'
    + '</div>';
}

function tc_postCol(teamName, sendsOut, receives, totalAfter) {
  var players = (TC.teams[teamName] || []).slice();
  var outNames = sendsOut.map(function(p){return p.name;});

  var html = '<div class="tc-post-col">';
  html += '<div class="tc-post-col-head">';
  html += _esc(teamName.substring(0,20)) + ' After Trade';
  html += '<span class="tc-post-col-total" style="color:var(--text2)">Σ ' + totalAfter.toFixed(0) + '</span>';
  html += '</div>';

  // Lost + kept players
  players.forEach(function(p) {
    var isOut = outNames.indexOf(p.name) !== -1;
    var rowCls = isOut ? 'tc-post-row tc-post-lost' : 'tc-post-row tc-post-kept';
    var marker = isOut ? 'out' : 'keep';
    var delta  = isOut ? '-' + p.base.toFixed(0) : '';
    var deltaCls = isOut ? 'neg' : '';
    var posFirst = (p.pos||'').split(',')[0].trim();
    html += '<div class="' + rowCls + '">';
    html += '<div class="tc-post-marker ' + marker + '"></div>';
    html += '<div class="tc-post-pos">' + _esc(posFirst) + '</div>';
    html += '<img class="tc-post-av" src="' + _esc(p.hs||'') + '" onerror="this.style.display=\'none\'">';
    html += '<div class="tc-post-name" onclick="openPlayerByName(\'' + _escQ(p.name) + '\')">' + _esc(p.name) + '</div>';
    html += '<div class="tc-post-score">' + p.base.toFixed(0) + '</div>';
    html += (delta ? '<div class="tc-post-delta ' + deltaCls + '">' + delta + '</div>' : '<div class="tc-post-delta"></div>');
    html += '</div>';
  });

  // Incoming players
  receives.forEach(function(p) {
    var posFirst = (p.pos||'').split(',')[0].trim();
    html += '<div class="tc-post-row tc-post-gained">';
    html += '<div class="tc-post-marker in"></div>';
    html += '<div class="tc-post-pos">' + _esc(posFirst) + '</div>';
    html += '<img class="tc-post-av" src="' + _esc(p.hs||'') + '" onerror="this.style.display=\'none\'">';
    html += '<div class="tc-post-name" onclick="openPlayerByName(\'' + _escQ(p.name) + '\')">' + _esc(p.name) + '</div>';
    html += '<div class="tc-post-score">' + p.base.toFixed(0) + '</div>';
    html += '<div class="tc-post-delta pos">+' + p.base.toFixed(0) + '</div>';
    html += '</div>';
  });

  html += '</div>';
  return html;
}

/* ── P6 Positional gap detection for trade calculator ────── */
function tc_getPositionalGaps(givingPlayers, myRoster) {
  var scarcePositions = ['C', 'SS', '2B'];
  var warnings = [];
  givingPlayers.forEach(function(p) {
    scarcePositions.forEach(function(pos) {
      if (p.pos && p.pos.indexOf(pos) !== -1) {
        // Check if we have replacements at this position
        var remaining = myRoster.filter(function(r) {
          return r.name !== p.name && r.pos && r.pos.indexOf(pos) !== -1;
        });
        if (remaining.length === 0) {
          warnings.push('Trading away your only ' + pos + ' (' + p.name + ') will leave a positional gap.');
        }
      }
    });
  });
  return warnings;
}

/* ── P6 ROS context pills ─────────────────────────────────── */
function tc_rosContext(player, weeksRemaining) {
  var pills = [];
  if (!player) return pills;
  // Age context
  if (player.age_tier) {
    var tierClass = player.age_tier <= 2 ? 'good' : (player.age_tier >= 4 ? 'warn' : '');
    var tierLabel = {1:'Pre-Peak', 2:'Prime', 3:'Peak', 4:'Decline', 5:'Late'}[player.age_tier] || '';
    if (tierLabel) pills.push({cls: tierClass, text: tierLabel + ' (age)'});
  }
  // Weeks remaining context
  if (weeksRemaining !== undefined) {
    pills.push({cls: '', text: weeksRemaining + ' wks left'});
  }
  // Injury flag
  if (player.status && player.status !== 'ACTIVE' && player.status !== 'NORMAL') {
    pills.push({cls: 'bad', text: '⚠ ' + player.status});
  }
  return pills;
}

function tc_renderRosPills(pills) {
  if (!pills || !pills.length) return '';
  return '<div class="tc-ros-bar">' + pills.map(function(p) {
    return '<span class="tc-ros-pill ' + (p.cls || '') + '">' + p.text + '</span>';
  }).join('') + '</div>';
}

/* ── P6 Render gap warnings ──────────────────────────────── */
function tc_renderGapWarnings(warnings) {
  if (!warnings || !warnings.length) return '';
  return warnings.map(function(w) {
    return '<div class="tc-gap-warn">' + w + '</div>';
  }).join('');
}

/* ── P6 Filter roster cards by name ──────────────────────── */
function tc_filterRosterCards(query) {
  var q = (query || '').toLowerCase();
  document.querySelectorAll('.tc-player-card, .tc-player, [data-player-name]').forEach(function(el) {
    var name = (el.dataset.playerName || el.textContent || '').toLowerCase();
    el.style.display = (!q || name.indexOf(q) !== -1) ? '' : 'none';
  });
}

/* ── Build the full Trade Calculator tab ────────────────── */
function buildTradeCalculator() {
  if (!TC.built) {
    tc_extractTeams();
    TC.built = true;
  }

  if (!TC.teamA) TC.teamA = TC.myTeam || TC.teamOrder[0] || '';
  if (!TC.teamB) TC.teamB = TC.teamOrder.find(function(t){return t !== TC.teamA;}) || '';

  var wrap = document.getElementById('tc-wrap');
  if (!wrap) return;

  function selOpts(sel, excl) {
    return TC.teamOrder.map(function(t) {
      var dis = t===excl ? ' disabled' : '';
      var selected = t===sel ? ' selected' : '';
      return '<option value="' + _esc(t) + '"' + selected + dis + '>' + _esc(t) + '</option>';
    }).join('');
  }

  var html = '';

  // Header
  html += '<div class="tc-header">';
  html += '<div class="tc-header-icon">🔄</div>';
  html += '<div><div class="tc-title">Trade Calculator</div>';
  html += '<div class="tc-subtitle">Click + or drag players into the baskets below &middot; analyze value, fit &amp; post-trade rosters &middot; all ' + TC.teamOrder.length + ' league teams accessible</div></div>';
  html += '</div>';

  // Team selector row
  html += '<div class="tc-team-row">';
  html += '<div class="tc-sel-group">';
  html += '<div class="tc-sel-label a">📋 Team A (Your Side)</div>';
  html += '<select class="tc-team-select a" onchange="tc_onTeamAChange(this.value)">' + selOpts(TC.teamA, TC.teamB) + '</select>';
  html += '</div>';
  html += '<div class="tc-vs-center">⇄</div>';
  html += '<div class="tc-sel-group">';
  html += '<div class="tc-sel-label b">📋 Team B (Trading Partner)</div>';
  html += '<select class="tc-team-select b" onchange="tc_onTeamBChange(this.value)">' + selOpts(TC.teamB, TC.teamA) + '</select>';
  html += '</div>';
  html += '</div>';

  // P6: Quick player filter
  html += '<div class="tc-scenario-bar">';
  html += '<label>🔍 Quick Player Filter</label>';
  html += '<input class="tc-filter" id="tc-filter-input" placeholder="Type player name to find them on your roster..." oninput="tc_filterRosterCards(this.value)" autocomplete="off">';
  html += '</div>';

  // Two-column roster tables
  html += '<div class="tc-tables">';
  html += '<div class="tc-tbl-card" id="tc-tbl-a">' + tc_buildTable('a', TC.teamA) + '</div>';
  html += '<div class="tc-tbl-card" id="tc-tbl-b">' + tc_buildTable('b', TC.teamB) + '</div>';
  html += '</div>';

  // Basket bar
  html += '<div class="tc-bbar"><div id="tc-bbar-inner">' + tc_buildBbar() + '</div></div>';

  // Result placeholder
  html += '<div id="tc-result" class="tc-result" style="display:none"></div>';

  wrap.innerHTML = html;
}

/* ── Helper: escape for HTML / JS string ───────────────── */
function _esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function _escQ(s) {
  return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
}

/* ── Lazy-build on tab open ─────────────────────────────── */
function tc_lazyBuild() {
  var wrap = document.getElementById('tc-wrap');
  if (!wrap || wrap.dataset.built) return;
  wrap.dataset.built = '1';
  buildTradeCalculator();
  setTimeout(_wireAllPlayerNames, 200);
}

// (tc_lazyBuild trigger now built into consolidated switchTab above)

/* ══════════════════════════════════════════════════════════════════════════
   LIVE SCORING FEED
   Fetches today's MLB box scores and shows per-player fantasy-point events
   inside the Live Matchup card, with a breakdown of how each point was earned.
══════════════════════════════════════════════════════════════════════════ */

var LS = {
  mine:     [],      // player objects from FDB_MATCHUP_PLAYERS.mine
  opp:      [],      // player objects from FDB_MATCHUP_PLAYERS.opp
  myName:   '',
  oppName:  '',
  loading:  false,
  interval: null,
  lastTs:   null,    // timestamp of last successful fetch
};

/* ── Bootstrap (called on DOMContentLoaded + on matchup tab open) ─────── */
function ls_init() {
  if (!window.FDB_MATCHUP_PLAYERS) return;
  LS.mine    = FDB_MATCHUP_PLAYERS.mine    || [];
  LS.myName  = FDB_MATCHUP_PLAYERS.myName  || 'My Team';
  LS.oppName = FDB_MATCHUP_PLAYERS.oppName || 'Opponent';

  // If server didn't embed opponent roster (e.g. cached HTML), build it from
  // the compare-section drag cards so opponent players still appear in the feed.
  var serverOpp = FDB_MATCHUP_PLAYERS.opp || [];
  if (serverOpp.length) {
    LS.opp = serverOpp;
  } else {
    var oppCards = document.querySelectorAll(
      '.drag-card[data-side="opp"][data-player], ' +
      '.opp-col .drag-card[data-player]'
    );
    var domOpp = [];
    oppCards.forEach(function (card) {
      var raw = card.getAttribute('data-player');
      if (!raw) return;
      try {
        var p = JSON.parse(raw);
        domOpp.push({
          name:  p.name  || p.player || '',
          isp:   !!(p.is_pitcher === 'true' || p.isp),
          mlbam: p.mlbam_id || p.mlbam || '',
          pos:   p.pos || '',
        });
      } catch (e) { /* malformed data-player attr — skip */ }
    });
    LS.opp = domOpp;
  }

  ls_refresh();

  // Auto-refresh every 90 s (pauses itself when no live games remain)
  if (!LS.interval) {
    LS.interval = setInterval(function () {
      if (document.querySelector('.tab-btn[data-tab="matchup"]') &&
          document.querySelector('#ipane-overview.visible')) {
        ls_refresh();
      }
    }, 90000);
  }
}

/* ── Today's date string (YYYY-MM-DD) ────────────────────────────────── */
function ls_today() {
  var d = new Date();
  return d.getFullYear() + '-'
    + String(d.getMonth() + 1).padStart(2, '0') + '-'
    + String(d.getDate()).padStart(2, '0');
}

/* ── Fetch MLB schedule + box scores for today ───────────────────────── */
// Two-step strategy:
//   1. GET /schedule to get today's gamePks and game states
//   2. GET /game/{pk}/boxscore for each Live/Final game in parallel
// This is more reliable than hydrate=boxscore which returns a lightweight
// structure that often lacks individual player stat lines.
function ls_refresh() {
  if (LS.loading) return;
  LS.loading = true;

  var schedUrl = 'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=' + ls_today();

  fetch(schedUrl)
    .then(function (r) { return r.json(); })
    .then(function (schedData) {
      // Collect gamePks for games that have started (Live or Final)
      var gamePks = [];
      (schedData.dates || []).forEach(function (d) {
        (d.games || []).forEach(function (g) {
          var state = (g.status && g.status.abstractGameState) || 'Preview';
          gamePks.push({ pk: g.gamePk, state: state });
        });
      });

      if (!gamePks.length) {
        LS.loading = false;
        LS.lastTs  = new Date();
        ls_renderBoxscores([]);
        return;
      }

      // Fetch individual boxscores for all today's games in parallel.
      // We fetch ALL games (not just Live/Final) so Preview boxscores still
      // populate the player list — they just have empty stats and get filtered.
      var requests = gamePks.map(function (g) {
        return fetch('https://statsapi.mlb.com/api/v1/game/' + g.pk + '/boxscore')
          .then(function (r) { return r.json(); })
          .then(function (bs) { return { boxscore: bs, state: g.state }; })
          .catch(function () { return null; });  // tolerate individual failures
      });

      Promise.all(requests).then(function (results) {
        LS.loading = false;
        LS.lastTs  = new Date();
        ls_renderBoxscores(results.filter(Boolean));
      });
    })
    .catch(function () {
      LS.loading = false;
      var feed = document.getElementById('live-scoring-feed');
      if (feed) feed.innerHTML =
        '<div class="ls-empty">Could not load scoring data — check your connection.</div>';
    });
}

/* ── Normalise a player name for fuzzy matching ──────────────────────── */
function ls_normName(s) {
  // Decompose accented chars (e.g. á → a + combining mark) then strip the
  // combining marks — so "Arráez" and "Arraez" both normalise to "arraez".
  return String(s || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/* ── IP notation converter ───────────────────────────────────────────── */
// MLB Stats API uses baseball notation: "5.2" means 5 innings + 2 outs = 5⅔ IP.
// The decimal digit is OUTS (0, 1, or 2), NOT a fractional inning.
// parseFloat('5.2') = 5.2 is WRONG; correct value is 5 + 2/3 = 5.667.
function ls_parseIP(ipStr) {
  var raw   = parseFloat(ipStr || '0');
  if (!raw || isNaN(raw)) return 0;
  var whole = Math.floor(raw);
  var outs  = Math.round((raw - whole) * 10); // .1 → 1 out, .2 → 2 outs
  return whole + outs / 3;
}

/* ── FP calculators (mirrors Python BATTING_SCORING / PITCHING_SCORING) ─ */
function ls_batFP(s) {
  // Use totalBases directly from the MLB API if present (most accurate).
  // Fall back to reconstructing from H/2B/3B/HR.
  var tb = (s.totalBases != null && s.totalBases > 0)
    ? s.totalBases
    : (s.hits || 0) + (s.doubles || 0) + (s.triples || 0) * 2 + (s.homeRuns || 0) * 3;
  return (s.runs          || 0) *  1
       + (s.homeRuns      || 0) *  1
       + tb                     *  1
       + (s.rbi           || 0) *  1
       + (s.baseOnBalls   || 0) *  1
       + (s.stolenBases   || 0) *  1
       + (s.strikeOuts    || 0) * -1;
}
function ls_pitFP(s) {
  // CRITICAL: convert MLB baseball IP notation (5.2 = 5⅔ IP) to true decimal.
  var ip  = ls_parseIP(s.inningsPitched);
  // Use qualityStarts from API directly; derive from IP/ER only as fallback.
  var qs  = (s.qualityStarts != null)
    ? (s.qualityStarts || 0)
    : (ip >= 6 && (s.earnedRuns || 0) <= 3) ? 1 : 0;
  var sv  = s.saves      || 0;
  var hd  = s.holds      || 0;
  // "SO" in PITCHING_SCORING = Shutout (9 pts), not strikeouts.
  // A shutout = complete game with 0 ER; use shutouts field from API.
  var sho = s.shutouts   || 0;
  return ip                    *  3
       + (s.hits          || 0) * -1
       + (s.earnedRuns    || 0) * -2
       + (s.homeRuns      || 0) * -1
       + (s.baseOnBalls   || 0) * -1
       + (s.strikeOuts    || 0) *  1
       + qs                     *  2
       + (s.wins          || 0) *  2
       + (s.losses        || 0) * -2
       + sv                     *  6
       + (s.blownSaves    || 0) * -3
       + hd                     *  5
       + (sv + hd)              *  2
       + sho                    *  9;  // shutout bonus
}

/* ── Build human-readable stat line ─────────────────────────────────── */
function ls_statLine(s, isp) {
  var parts = [];
  if (isp) {
    var ip = s.inningsPitched || '0';
    parts.push(ip + ' IP');
    if (s.hits          !== undefined) parts.push(s.hits + ' H');
    if (s.earnedRuns    !== undefined) parts.push(s.earnedRuns + ' ER');
    if (s.strikeOuts    !== undefined) parts.push(s.strikeOuts + ' K');
    if (s.baseOnBalls   !== undefined && s.baseOnBalls > 0) parts.push(s.baseOnBalls + ' BB');
    if (s.wins          > 0)  parts.push('W');
    if (s.losses        > 0)  parts.push('L');
    if (s.saves         > 0)  parts.push(s.saves + ' SV');
    if (s.holds         > 0)  parts.push(s.holds + ' HD');
    if (s.blownSaves    > 0)  parts.push(s.blownSaves + ' BS');
  } else {
    var h  = s.hits       || 0;
    var ab = s.atBats     || 0;
    if (ab > 0) parts.push(h + '-for-' + ab);
    if (s.homeRuns    > 0) parts.push(s.homeRuns    + ' HR');
    if (s.triples     > 0) parts.push(s.triples     + ' 3B');
    if (s.doubles     > 0) parts.push(s.doubles     + ' 2B');
    if (s.runs        > 0) parts.push(s.runs        + ' R');
    if (s.rbi         > 0) parts.push(s.rbi         + ' RBI');
    if (s.baseOnBalls > 0) parts.push(s.baseOnBalls + ' BB');
    if (s.stolenBases > 0) parts.push(s.stolenBases + ' SB');
    if (s.strikeOuts  > 0) parts.push(s.strikeOuts  + ' K');
  }
  return parts.join(', ') || '—';
}

/* ── Build FP breakdown explanation ─────────────────────────────────── */
function ls_breakdown(s, isp) {
  var parts = [];
  if (isp) {
    // Use ls_parseIP so IP math matches the scoring formula (5.2 = 5⅔ not 5.2)
    var ip    = ls_parseIP(s.inningsPitched);
    var ipPts = ip * 3;
    if (ip > 0)  parts.push((s.inningsPitched || '0') + ' IP = +' + ipPts.toFixed(1));
    if ((s.strikeOuts || 0) > 0)   parts.push(s.strikeOuts + ' K = +' + s.strikeOuts);
    if ((s.wins || 0) > 0)         parts.push('W = +2');
    if ((s.saves || 0) > 0)        parts.push(s.saves + ' SV = +' + (s.saves * 8));  // SV×6 + SVHD×2
    if ((s.holds || 0) > 0)        parts.push(s.holds + ' HD = +' + (s.holds * 7));  // HD×5 + SVHD×2
    var qs = (s.qualityStarts != null) ? (s.qualityStarts || 0) : (ip >= 6 && (s.earnedRuns || 0) <= 3 ? 1 : 0);
    if (qs > 0)                    parts.push('QS = +2');
    if ((s.shutouts || 0) > 0)     parts.push('SHO = +9');
    var neg = [];
    if ((s.hits || 0) > 0)         neg.push(s.hits + ' H = -' + s.hits);
    if ((s.earnedRuns || 0) > 0)   neg.push(s.earnedRuns + ' ER = -' + (s.earnedRuns * 2));
    if ((s.homeRuns || 0) > 0)     neg.push(s.homeRuns + ' HR = -' + s.homeRuns);
    if ((s.baseOnBalls || 0) > 0)  neg.push(s.baseOnBalls + ' BB = -' + s.baseOnBalls);
    if ((s.losses || 0) > 0)       neg.push('L = -2');
    if ((s.blownSaves || 0) > 0)   neg.push(s.blownSaves + ' BS = -' + (s.blownSaves * 3));
    parts = parts.concat(neg);
  } else {
    var tb = (s.totalBases != null && s.totalBases > 0)
      ? s.totalBases
      : (s.hits || 0) + (s.doubles || 0) + (s.triples || 0) * 2 + (s.homeRuns || 0) * 3;
    if (tb > 0)                    parts.push(tb + ' TB = +' + tb);
    if ((s.homeRuns || 0) > 0)     parts.push(s.homeRuns + ' HR = +' + s.homeRuns);
    if ((s.runs || 0) > 0)         parts.push(s.runs + ' R = +' + s.runs);
    if ((s.rbi || 0) > 0)          parts.push(s.rbi + ' RBI = +' + s.rbi);
    if ((s.baseOnBalls || 0) > 0)  parts.push(s.baseOnBalls + ' BB = +' + s.baseOnBalls);
    if ((s.stolenBases || 0) > 0)  parts.push(s.stolenBases + ' SB = +' + s.stolenBases);
    if ((s.strikeOuts || 0) > 0)   parts.push(s.strikeOuts + ' K = -' + s.strikeOuts);
  }
  return parts.slice(0, 6).join(' · ');  // cap at 6 items to keep compact
}

/* ── Build avatar HTML for a player ─────────────────────────────────── */
function ls_avatar(p) {
  if (p.hs) {
    var err = p.hs2
      ? 'this.src=\'' + p.hs2 + '\';this.onerror=function(){this.style.display=\'none\';this.nextSibling.style.display=\'flex\';};'
      : 'this.style.display=\'none\';this.nextSibling.style.display=\'flex\';';
    return '<img class="ls-av" src="' + _esc(p.hs) + '" alt="' + _esc(p.name) + '" '
         + 'onerror="' + err + '">'
         + '<div class="ls-av-fb" style="display:none">' + _esc(p.ini) + '</div>';
  }
  return '<div class="ls-av-fb">' + _esc(p.ini) + '</div>';
}

/* ── Render one player scoring event ─────────────────────────────────── */
function ls_eventHtml(ev) {
  var fp    = ev.fp;
  var fpStr = (fp > 0 ? '+' : '') + fp.toFixed(1);
  var fpCls = fp > 0 ? 'pos' : fp < 0 ? 'neg' : 'zero';
  var evCls = fp > 0 ? 'fp-pos' : fp < 0 ? 'fp-neg' : 'fp-zero';

  var gameBadge = '';
  if (ev.gameState === 'Live') {
    gameBadge = '<span class="ls-game-badge ls-game-live">LIVE</span>';
  } else if (ev.gameState === 'Final') {
    gameBadge = '<span class="ls-game-badge ls-game-final">FINAL</span>';
  }

  var statline  = ls_statLine(ev.stats, ev.isp);
  var bdown     = ls_breakdown(ev.stats, ev.isp);
  var bdownHtml = bdown
    ? '<div class="ls-breakdown">' + _esc(bdown) + '</div>'
    : '';

  // Make name clickable to open player modal (if data attrs are available)
  var nameHtml = ev.player.mlbam
    ? '<span class="ls-name" data-mlbam="' + _esc(ev.player.mlbam) + '">'
      + _esc(ev.player.name) + '</span>'
    : '<span class="ls-name">' + _esc(ev.player.name) + '</span>';

  return '<div class="ls-event ' + evCls + '">'
       +   ls_avatar(ev.player)
       +   '<div class="ls-body">'
       +     nameHtml
       +     '<div class="ls-statline">'
       +       _esc(statline)
       +       gameBadge
       +     '</div>'
       +     bdownHtml
       +   '</div>'
       +   '<div class="ls-fp ' + fpCls + '">' + _esc(fpStr) + '</div>'
       + '</div>';
}

/* ── Main render ─────────────────────────────────────────────────────── */
// ls_render kept as alias for backwards compat (not used by new ls_refresh)
function ls_render(scheduleData) { ls_renderBoxscores([]); }

/* ── Main render — consumes array of {boxscore, state} objects ───────── */
function ls_renderBoxscores(results) {
  var feed = document.getElementById('live-scoring-feed');
  if (!feed) return;

  // ── Build name/MLBAM → {pitching, batting, gameState} map ────────────
  var byName   = {};   // normalised name  → entry
  var byMlbam  = {};   // mlbam id string  → entry
  var hasLive  = false;
  var totalBoxPlayers = 0;

  results.forEach(function (item) {
    var abstract = item.state || 'Preview';
    if (abstract === 'Live') hasLive = true;

    // Direct boxscore endpoint returns: {teams:{home:{players:{ID123:{...}}}, away:{...}}}
    var teams = (item.boxscore && item.boxscore.teams) || {};

    ['away', 'home'].forEach(function (side) {
      var teamBox = teams[side] || {};
      var players = teamBox.players || {};

      Object.values(players).forEach(function (p) {
        var id    = String((p.person && p.person.id) || '');
        var fname = (p.person && p.person.fullName)  || '';
        if (!id && !fname) return;
        totalBoxPlayers++;

        // Store BOTH pitching and batting stats — select by p.isp at match time.
        var entry = {
          pitching:  (p.stats && p.stats.pitching) || {},
          batting:   (p.stats && p.stats.batting)  || {},
          gameState: abstract,
        };
        if (id)    byMlbam[id]               = entry;
        if (fname) byName[ls_normName(fname)] = entry;
      });
    });
  });

  /* ── Match roster players to box score entries ───────────────────────── */
  function matchPlayer(p) {
    var id = String(p.mlbam || '');
    if (id) {
      var byId = byMlbam[id];
      if (byId) return byId;
    }
    return byName[ls_normName(p.name)] || null;
  }

  function buildEvents(players) {
    var events = [];
    players.forEach(function (p) {
      var raw = matchPlayer(p);
      if (!raw) return;

      // Use correct stat block based on roster pitcher/hitter flag.
      var stats = p.isp ? raw.pitching : raw.batting;

      // Only include players who have actually participated:
      //   Pitchers: at least 1 out recorded (ip > 0)
      //   Hitters:  at least 1 plate appearance
      var hasPlayed = p.isp
        ? ls_parseIP(stats.inningsPitched) > 0
        : ((stats.atBats || 0) + (stats.baseOnBalls || 0) + (stats.hitByPitch || 0)) > 0;
      if (!hasPlayed) return;

      var fp = p.isp ? ls_pitFP(stats) : ls_batFP(stats);
      events.push({ player: p, stats: stats, isp: p.isp,
                    fp: fp, gameState: raw.gameState });
    });
    events.sort(function (a, b) { return b.fp - a.fp; });
    return events;
  }

  var mineEvents = buildEvents(LS.mine);
  var oppEvents  = buildEvents(LS.opp);

  /* ── Nothing yet — show diagnostic info ─────────────────────────────── */
  if (!mineEvents.length && !oppEvents.length) {
    var diagMsg = results.length === 0
      ? 'No games found for today.'
      : 'Games loaded (' + results.length + ') — ' + totalBoxPlayers + ' players in box scores. '
        + (LS.mine.length + LS.opp.length === 0
          ? 'No roster players loaded.'
          : 'No roster players have batted or pitched yet — check back once play begins.');
    feed.innerHTML = '<div class="ls-section">'
      + '<div class="ls-section-title">'
      + '<span class="ls-pulse"></span>Today\'s Scoring Events'
      + '</div>'
      + '<div class="ls-empty">' + diagMsg + '</div>'
      + ls_footerHtml(false)
      + '</div>';
    return;
  }

  /* ── Today's FP totals ───────────────────────────────────────────────── */
  var myFP  = mineEvents.reduce(function (s, e) { return s + e.fp; }, 0);
  var oppFP = oppEvents.reduce(function (s, e)  { return s + e.fp; }, 0);

  /* ── Build HTML ──────────────────────────────────────────────────────── */
  var pulseCls = hasLive ? 'ls-pulse live' : 'ls-pulse final';

  var html = '<div class="ls-section">';
  html += '<div class="ls-section-title">'
        + '<span class="' + pulseCls + '"></span>'
        + (hasLive ? 'Live Scoring Events' : 'Today\'s Scoring Events')
        + '</div>';

  // Two-column layout
  html += '<div class="ls-columns">';

  // My team column
  html += '<div>';
  html += '<div class="ls-col-head mine">' + _esc(LS.myName) + '</div>';
  if (mineEvents.length) {
    mineEvents.forEach(function (ev) { html += ls_eventHtml(ev); });
  } else {
    html += '<div class="ls-empty">No stats yet today</div>';
  }
  html += '</div>';

  // Opponent column
  html += '<div>';
  html += '<div class="ls-col-head opp">' + _esc(LS.oppName) + '</div>';
  if (oppEvents.length) {
    oppEvents.forEach(function (ev) { html += ls_eventHtml(ev); });
  } else {
    html += '<div class="ls-empty">No stats yet today</div>';
  }
  html += '</div>';

  html += '</div>'; // .ls-columns

  // Today's FP totals
  html += '<div class="ls-totals">';
  var myFpCls  = myFP  > 0 ? 'pos' : myFP  < 0 ? 'neg' : 'zero';
  var oppFpCls = oppFP > 0 ? 'pos' : oppFP < 0 ? 'neg' : 'zero';
  html += '<div class="ls-total-box">'
        + '<div class="ls-total-lbl">Today\'s FP</div>'
        + '<div class="ls-total-val ' + myFpCls  + '">' + (myFP  >= 0 ? '+' : '') + myFP.toFixed(1)  + '</div>'
        + '</div>';
  html += '<div class="ls-total-box">'
        + '<div class="ls-total-lbl">Today\'s FP</div>'
        + '<div class="ls-total-val ' + oppFpCls + '">' + (oppFP >= 0 ? '+' : '') + oppFP.toFixed(1) + '</div>'
        + '</div>';
  html += '</div>'; // .ls-totals

  html += ls_footerHtml(hasLive);
  html += '</div>'; // .ls-section

  feed.innerHTML = html;

  // Wire player names to open modal
  feed.querySelectorAll('.ls-name[data-mlbam]').forEach(function (el) {
    el.addEventListener('click', function () {
      var fake = document.createElement('div');
      fake.dataset.mlbam = el.dataset.mlbam;
      fake.dataset.name  = el.textContent;
      var fakeEv = { stopPropagation: function(){} };
      openPlayerModal(fakeEv, el.closest('.ls-event') || fake);
    });
  });
}

/* ── Footer: last-updated + manual refresh button ────────────────────── */
function ls_footerHtml(hasLive) {
  var ts = LS.lastTs
    ? LS.lastTs.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';
  var autoNote = hasLive ? ' · auto-refreshes every 90s' : '';
  return '<div class="ls-refresh-row">'
       + '<span>' + (ts ? 'Updated ' + ts + autoNote : '') + '</span>'
       + '<button class="ls-refresh-btn" onclick="ls_refresh()">↻ Refresh</button>'
       + '</div>';
}

/* ── Trigger init when matchup tab is opened ─────────────────────────── */
window.addEventListener('DOMContentLoaded', function () {
  // Init immediately if page opens on matchup tab
  if (document.querySelector('.tab-pane[data-tab="matchup"].visible') ||
      localStorage.getItem('fdb_tab') === 'today') {
    ls_init();
  }
});

// Also init when user clicks to the matchup tab
(function () {
  var _origSwitchTab = switchTab;
  switchTab = function (tab) {
    _origSwitchTab(tab);
    if (tab === 'today' && !LS.interval) {
      ls_init();
    }
  };
})();

// ── Waiver sub-tab switcher ───────────────────────────────────────────────
function switchWaiverTab(tab) {
  ['hitters', 'pitchers'].forEach(function(t) {
    var btn = document.getElementById('wstb-' + t);
    var pane = document.getElementById('wpane-' + t);
    if (btn)  btn.classList.toggle('active', t === tab);
    if (pane) pane.classList.toggle('visible', t === tab);
  });
}

// ── Roster view toggle (Grid | Compact | List) ────────────────────────────
function rcToggle(secId, mode, btn) {
  var grid    = document.getElementById(secId + '-grid');
  var list    = document.getElementById(secId + '-list');
  var btns    = document.getElementById(secId + '-btns');

  // Update active button highlight
  if (btns) btns.querySelectorAll('.rc-view-btn').forEach(function(b) {
    b.classList.remove('active');
  });
  if (btn) btn.classList.add('active');

  if (mode === 'list') {
    if (grid) grid.style.display = 'none';
    if (list) list.style.display = 'block';
    // Remove compact class from body if switching to list
    document.body.classList.remove('compact-roster');
  } else if (mode === 'compact') {
    if (grid) grid.style.display = '';
    if (list) list.style.display = 'none';
    document.body.classList.add('compact-roster');
  } else {
    // grid (default)
    if (grid) grid.style.display = '';
    if (list) list.style.display = 'none';
    document.body.classList.remove('compact-roster');
  }

  // Persist preference per section
  try { localStorage.setItem('fdb_rc_' + secId, mode); } catch(e) {}
}

// Restore roster view preferences on load
window.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[id$="-btns"].rc-view-btns').forEach(function(btnsEl) {
    var secId = btnsEl.id.replace('-btns', '');
    var saved;
    try { saved = localStorage.getItem('fdb_rc_' + secId); } catch(e) {}
    if (saved && saved !== 'grid') {
      var targetBtn = btnsEl.querySelector('[onclick*="' + saved + '"]');
      rcToggle(secId, saved, targetBtn);
    }
  });
});
