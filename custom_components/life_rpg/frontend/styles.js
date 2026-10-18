/* Life RPG stylesheets, kept apart from the panel's code so either is easier to read.
 * Everything is scoped by the shadow DOM of the panel or card that uses it. */

// Shared by the panel and the cards: the System windows, bars, buttons, chips, quests, art and every tab.
export const CSS = `
  :host{--abyss:#040815;--blue:#45b8ff;--ice:#ddf3ff;--dim:#8fa8c4;--violet:#7b5cff;--red:#ff3d57;--gold:#f5c451;--win:rgba(9,22,44,.8);
    display:block;color:var(--ice);font-family:var(--paper-font-body1_-_font-family,Roboto,system-ui,sans-serif);font-size:14px;line-height:1.45}
  *{box-sizing:border-box}
  button{font:inherit;color:inherit;cursor:pointer}
  button:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
  img.doll,img.mon,.icon img{image-rendering:pixelated;image-rendering:crisp-edges;display:block}
  .win{position:relative;background:var(--win);border:1px solid rgba(69,184,255,.55);border-radius:4px;padding:16px;
    box-shadow:0 0 0 1px rgba(69,184,255,.08) inset,0 0 18px rgba(69,184,255,.18);backdrop-filter:blur(6px)}
  .win::before,.win::after{content:"";position:absolute;width:14px;height:14px;border:2px solid var(--blue);pointer-events:none}
  .win::before{top:-2px;left:-2px;border-right:0;border-bottom:0}
  .win::after{bottom:-2px;right:-2px;border-left:0;border-top:0}
  .win.red{border-color:rgba(255,61,87,.7);background:rgba(40,8,16,.82);box-shadow:0 0 22px rgba(255,61,87,.25)}
  .win.red::before,.win.red::after{border-color:var(--red)}
  .win.gold{border-color:rgba(245,196,81,.6)} .win.gold::before,.win.gold::after{border-color:var(--gold)}
  .win.violet{border-color:rgba(123,92,255,.6)} .win.violet::before,.win.violet::after{border-color:var(--violet)}
  .wt{display:flex;justify-content:center;align-items:center;gap:8px;margin:-2px 0 14px;font-size:13px;letter-spacing:.18em;font-weight:600;color:#bfe6ff;text-shadow:0 0 8px rgba(69,184,255,.8)}
  .wt::before{content:"[";opacity:.7} .wt::after{content:"]";opacity:.7}
  .red .wt{color:#ffc2ca;text-shadow:0 0 8px rgba(255,61,87,.9)}
  .gold .wt{color:#ffe3a1;text-shadow:0 0 8px rgba(245,196,81,.9)} .violet .wt{color:#d9ccff;text-shadow:0 0 8px rgba(123,92,255,.9)}
  .muted{color:var(--dim)} .small{font-size:12px} .gold-t{color:var(--gold)}
  .bar{height:8px;background:rgba(69,184,255,.12);border:1px solid rgba(69,184,255,.35);border-radius:2px;overflow:hidden}
  .bar i{display:block;height:100%;background:linear-gradient(90deg,#1f6fd1,var(--blue));box-shadow:0 0 8px var(--blue)}
  .bar.gold i{background:linear-gradient(90deg,#b8852a,var(--gold));box-shadow:0 0 8px var(--gold)}
  .bar.red i{background:linear-gradient(90deg,#9b1a2c,var(--red));box-shadow:0 0 8px var(--red)}
  .bar.violet i{background:linear-gradient(90deg,#4630b8,var(--violet))}
  .bar.thick{height:12px}
  .btn{background:rgba(69,184,255,.12);border:1px solid rgba(69,184,255,.6);border-radius:3px;padding:7px 14px;color:var(--ice)}
  .btn:hover{background:rgba(69,184,255,.24)} .btn.gold{border-color:var(--gold);background:rgba(245,196,81,.14)}
  .btn.ghost{border-color:transparent;background:none;color:var(--dim)} .btn.ghost:hover{color:var(--ice)} .btn:disabled{opacity:.4;cursor:default}
  .row{display:flex;gap:12px;align-items:center} .between{justify-content:space-between} .wrap{flex-wrap:wrap} .center-row{justify-content:center}
  .grid{display:grid;gap:16px}
  .stack>*+*{margin-top:12px}
  ha-icon{--mdc-icon-size:20px}
  .center-text{text-align:center} .big-line{font-size:16px;color:#fff;text-align:center}
  /* status */
  .episode{margin:-6px 0 12px;text-align:center;font-style:italic;color:#bfe6ff;opacity:.85}
  .status{display:grid;grid-template-columns:auto 1fr;gap:20px;align-items:center}
  .portrait-col{display:grid;justify-items:center;gap:4px}
  .stage{position:relative;display:grid;justify-items:center;padding-top:8px;contain:paint;isolation:isolate;
    background:radial-gradient(closest-side at 50% 55%,color-mix(in srgb,var(--aura) 32%,transparent),transparent)}
  .stage::after{content:"";position:absolute;left:18%;right:18%;bottom:2px;height:10px;border-radius:50%;
    background:radial-gradient(closest-side,color-mix(in srgb,var(--aura) 55%,transparent),transparent);z-index:0}
  .stage img{position:relative;z-index:1;animation:bob 1.6s steps(2) infinite;will-change:transform}
  @keyframes bob{50%{transform:translateY(-3px)}}
  .lvl{display:flex;align-items:baseline;gap:10px}
  .lvl b{font-size:64px;font-weight:200;line-height:.9;color:#fff;text-shadow:0 0 18px rgba(69,184,255,.9)}
  .lvl span{letter-spacing:.2em;color:var(--dim);font-size:12px;text-transform:uppercase}
  .name{font-size:22px;font-weight:500;color:#fff}
  .mk{width:28px} .pv{width:40px;text-align:right;font-variant-numeric:tabular-nums}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:13px;margin-left:0;margin-right:0;margin-bottom:0} .kv dt{color:var(--dim)} .kv dd{margin:0}
  .attrs{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
  .attr{display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid rgba(69,184,255,.25);border-radius:3px;background:rgba(69,184,255,.05)}
  .attr b{font-size:20px;font-weight:600;margin-left:auto}
  .skills{display:grid;gap:10px} .skill .grade{font-size:12px;color:#d9ccff}
  .sources{margin-top:10px} .sources summary{cursor:pointer;color:var(--dim)} .sources summary:hover{color:var(--ice)}
  .src{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr);gap:10px;padding:5px 0;border-bottom:1px dashed rgba(69,184,255,.15)}
  .sources p{margin:6px 0 0} .capnote{margin:8px 0 0;color:#ffe3a1}
  .chips{display:flex;flex-wrap:wrap;gap:6px} .chip{font-size:12px;padding:3px 8px;border-radius:999px;background:rgba(69,184,255,.12);border:1px solid rgba(69,184,255,.3)}
  .chip.gold{background:rgba(245,196,81,.12);border-color:rgba(245,196,81,.4);color:#ffe6a6}
  .chip.red{background:rgba(255,61,87,.14);border-color:rgba(255,61,87,.5);color:#ffc2ca}
  .chip.el{border-color:var(--ec);color:var(--ec);background:color-mix(in srgb,var(--ec) 12%,transparent)}
  .count{font-size:30px;font-weight:200;color:#fff;font-variant-numeric:tabular-nums;text-align:center}
  blockquote{margin:0;padding:12px 14px;border-left:2px solid #c9b8ff;background:rgba(123,92,255,.08);font-style:italic;color:#ece6ff}
  /* choice */
  .choice .voice{margin:0 0 8px;text-align:center;font-style:italic;color:#d9ccff}
  .choice .offer{margin:0 0 14px;text-align:center;font-size:16px;color:#fff}
  /* quests */
  .q{display:grid;grid-template-columns:28px 1fr auto;gap:4px 12px;align-items:center;padding:8px 0;border-bottom:1px dashed rgba(69,184,255,.18)}
  .q:last-of-type{border-bottom:0} .q .bar{grid-column:2/4}
  .q .val{font-variant-numeric:tabular-nums;color:#fff} .q.done .val{color:var(--gold)}
  .check{width:22px;height:22px;border:1.5px solid var(--blue);border-radius:3px;display:grid;place-items:center}
  .done .check{background:var(--gold);border-color:var(--gold);color:#1a1200}
  .warn{color:#ff9aa8;font-size:12px;text-align:center;margin:12px 0 0}
  /* labyrinth */
  .guardian{display:grid;grid-template-columns:auto 1fr;gap:18px;align-items:center}
  .lair{position:relative;display:grid;place-items:center;padding:8px;border-radius:4px;
    background:radial-gradient(closest-side,color-mix(in srgb,var(--ec) 30%,transparent),transparent),
      repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 12px),repeating-linear-gradient(90deg,rgba(255,255,255,.03) 0 1px,transparent 1px 12px)}
  .lair{contain:paint;isolation:isolate}
  .lair img{animation:bob 2.2s steps(2) infinite;will-change:transform}
  .lair.felled img{filter:grayscale(1) brightness(.5);animation:none}
  .felled-tag{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) rotate(-12deg);padding:2px 10px;border:2px solid var(--gold);color:var(--gold);font-weight:700;letter-spacing:.1em;background:rgba(4,8,21,.75)}
  .trait{padding:8px 10px;border-left:2px solid var(--violet);background:rgba(123,92,255,.08)}
  .depth{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center}
  .bestiary{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:8px}
  .beast{display:grid;justify-items:center;gap:2px;padding:8px 6px;border:1px solid rgba(123,92,255,.35);border-radius:3px;background:rgba(123,92,255,.06);font-size:12px;text-align:center}
  .beast.elite{border-color:rgba(245,196,81,.55)} .beast.cursed{border-color:rgba(255,61,87,.55);background:rgba(255,61,87,.06)}
  .kinds{display:grid;grid-template-columns:repeat(auto-fill,minmax(70px,1fr));gap:6px}
  .kind{display:grid;justify-items:center;font-size:11px;color:var(--dim)} .kind.unseen img{filter:brightness(0) drop-shadow(0 0 1px #45b8ff);opacity:.6}
  .kind b{color:#fff;font-size:13px}
  /* inventory */
  .doll{display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:center;justify-items:center}
  .slots{display:grid;gap:8px} .slotbtn{background:none;border:0;padding:0;display:block}
  .icon{position:relative;display:inline-grid;place-items:center;border:2px solid var(--rc);border-radius:4px;
    background:radial-gradient(closest-side,color-mix(in srgb,var(--rc) 28%,transparent),color-mix(in srgb,var(--rc) 6%,#040815))}
  .icon.empty{border:1px dashed #2a3b57;background:rgba(42,59,87,.12);color:#3a4f73}
  .icon.r-epic,.icon.r-legendary,.icon.r-mythic{box-shadow:0 0 10px color-mix(in srgb,var(--rc) 60%,transparent)}
  .icon.r-mythic{animation:prism 6s linear infinite}
  @keyframes prism{to{filter:hue-rotate(360deg)}}
  .icon .enh{position:absolute;right:2px;bottom:0;font-size:11px;color:#fff;text-shadow:0 0 3px #000,0 0 3px #000}
  .inv{display:grid;grid-template-columns:repeat(auto-fill,minmax(56px,1fr));gap:8px;justify-items:center}
  .inv button{background:none;border:0;padding:0;position:relative}
  .inv button[aria-pressed="true"] .icon{outline:2px solid #fff;outline-offset:2px}
  .inv .eq::after{content:"E";position:absolute;top:-4px;left:-4px;width:16px;height:16px;border-radius:50%;background:var(--gold);color:#1a1200;font-size:10px;font-weight:700;display:grid;place-items:center}
  .detail h3{margin:0 0 4px;font-size:17px} .rarity{font-size:12px;letter-spacing:.12em;text-transform:uppercase}
  .chests{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
  .chestbtn{background:none;border:0;padding:0;display:grid;justify-items:center;font-size:11px;color:var(--dim)}
  .chestbtn:hover .chest{transform:translateY(-2px)}
  .reveal{text-align:center} .reveal .chest{margin:0 auto}.reveal .chest .lid{animation:lid .6s ease-out forwards;transform-box:fill-box;transform-origin:0 100%}
  @keyframes lid{to{transform:translateY(-4px) rotate(-18deg);opacity:.4}}
  .burst{animation:burst .9s ease-out;position:relative;display:grid;justify-items:center}
  .rays{position:absolute;left:50%;top:52px;width:240px;height:240px;margin:-120px 0 0 -120px;pointer-events:none;
    background:repeating-conic-gradient(from 0deg,var(--rc) 0 6deg,transparent 6deg 24deg);opacity:.35;
    -webkit-mask:radial-gradient(circle,#000 0,transparent 68%);mask:radial-gradient(circle,#000 0,transparent 68%);animation:spin 14s linear infinite}
  .burst .icon{position:relative}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes burst{from{transform:scale(.6);opacity:0;filter:brightness(3)}to{transform:none;opacity:1}}
  /* class */
  .jobs{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:12px}
  .job{display:grid;gap:8px;padding:12px;border:1px solid rgba(69,184,255,.25);border-radius:3px;background:rgba(69,184,255,.04)}
  .job.active{border-color:var(--gold);box-shadow:0 0 14px rgba(245,196,81,.22);background:rgba(245,196,81,.05)}
  .job.rec{border-color:rgba(123,92,255,.7)}
  .job .head{display:flex;gap:10px;align-items:center}
  .job .jicon{width:40px;height:40px;display:grid;place-items:center;border-radius:50%;border:1px solid currentColor;color:#9fd8ff;flex:none}
  .job.active .jicon{color:var(--gold)}
  .job ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
  .job li{display:grid;grid-template-columns:40px 1fr;gap:6px;font-size:12px} .job li.off{opacity:.45}
  .job li span{color:var(--dim);font-variant-numeric:tabular-nums}
  /* records */
  .titles{display:grid;gap:8px} .title{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:10px;border:1px solid rgba(69,184,255,.2);border-radius:3px}
  .title.earned{border-color:rgba(245,196,81,.45);background:rgba(245,196,81,.05)} .title.eqd{box-shadow:0 0 0 1px var(--gold) inset}
  .badges{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
  .badge{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;align-items:center;padding:8px;border:1px solid rgba(69,184,255,.18);border-radius:3px}
  .badge .bar{grid-column:1/3}
  .medal{position:relative;width:58px;height:58px;display:grid;place-items:center} .medal svg{position:absolute;inset:0}
  .medal ha-icon{color:var(--c);--mdc-icon-size:24px;filter:drop-shadow(0 0 4px var(--c))} .medal.locked ha-icon{opacity:.35}
  .medal .stars{position:absolute;bottom:-4px;font-style:normal;font-size:10px;color:#fff;background:#14325a;border:1px solid var(--c);border-radius:8px;padding:0 4px}
  .hidden{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
  .hq{padding:10px;border:1px solid rgba(123,92,255,.45);border-radius:3px;font-size:13px;background:rgba(123,92,255,.1)}
  /* goddess */
  .goddess{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:18px;align-items:center}
  .sigil{width:100%;height:auto}
  .tree{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .node{padding:10px;border:1px solid rgba(69,184,255,.2);border-radius:3px;font-size:13px}
  .node.on{border-color:var(--gold);box-shadow:0 0 12px rgba(245,196,81,.25)} .node.off{opacity:.45}
  .node.root{grid-column:1/3;text-align:center}
  .blessing{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px dashed rgba(123,92,255,.25)}
  .blessing.off{opacity:.45}
  /* log */
  .log{list-style:none;margin:0;padding:0} .log li{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;padding:8px 0;border-bottom:1px solid rgba(69,184,255,.1)}
  .log time{color:var(--dim);font-size:12px;grid-row:1/3} .log b{font-weight:600}
  .hist{width:100%;height:110px;display:block} .legend{display:flex;gap:14px;font-size:12px;color:var(--dim)} .legend i{display:inline-block;width:10px;height:10px;margin-right:6px;border-radius:2px}
  /* toasts */
  .toasts{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:9;display:grid;gap:10px;width:min(440px,calc(100vw - 32px));pointer-events:none}
  .toast{pointer-events:auto;text-align:center;animation:pop .45s cubic-bezier(.2,1.4,.4,1);background:rgba(6,16,34,.95)}
  .toast .msg{font-size:15px} .toast.big .msg{font-size:18px;color:#fff}
  @keyframes pop{from{transform:scaleY(.05);opacity:0;filter:brightness(2.5)}to{transform:none;opacity:1}}
  /* painted art */
  .painted-stage{padding:0;background:none}
  .painted-stage::after{display:none}
  .crop{display:block;position:relative;overflow:hidden;aspect-ratio:var(--ar)}
  .crop img{position:absolute;left:50%;top:0;width:calc(var(--z) * 100%);max-width:none;height:auto;transform:translateX(-50%);animation:none;image-rendering:auto}
  .stage .painted{width:100%;border-radius:6px;animation:none;
    filter:none;box-shadow:0 0 0 1px rgba(69,184,255,.35),0 10px 30px rgba(0,0,0,.5),0 0 40px color-mix(in srgb,var(--aura) 35%,transparent)}
  .frame-silver .painted{border:3px solid #c9d1da;box-shadow:0 0 0 2px #6c7a8a,0 0 18px rgba(201,209,218,.4)}
  .frame-gold .painted{border:3px solid #f5c451;box-shadow:0 0 0 2px #8a6a1e,0 0 22px rgba(245,196,81,.45)}
  .frame-moon .painted{border:3px solid #c9b8ff;box-shadow:0 0 0 2px #4a3b8a,0 0 26px rgba(180,156,255,.6)}
  .frame-thorn .painted{border:3px dashed #6b8f4e;box-shadow:0 0 0 3px #2a3b1e}
  .frame-dragon .painted{border:4px double #e6dcc4;box-shadow:0 0 0 2px #5a1e1e,0 0 22px rgba(255,90,90,.35)}
  .paint-badge{position:absolute;left:50%;bottom:8px;transform:translateX(-50%);white-space:nowrap;font-size:11px;padding:3px 8px;border-radius:999px;
    background:rgba(4,8,21,.85);border:1px solid rgba(123,92,255,.6);color:#d9ccff;z-index:2}
  .icon img.paint{image-rendering:auto;border-radius:3px;object-fit:cover}
  img.mon.paint{image-rendering:auto;border-radius:8px;object-fit:cover;box-shadow:0 0 14px var(--mg)}
  .lair img.mon.paint{animation:none}
  .studio{margin:0;text-align:center} .warn-t{color:#ff9aa8} .tight{gap:6px}
  img.pix,.cicon img,.bust{image-rendering:pixelated;image-rendering:crisp-edges}
  .bust{display:inline-block;background-repeat:no-repeat;flex:none;background-color:rgba(123,92,255,.14)}
  .npc .bust{border-radius:50%;border:2px solid rgba(123,92,255,.6)} .bust.npc-portrait{background-color:rgba(245,196,81,.1)}
  img.lune.pix{width:192px;max-width:none;height:252px;box-shadow:none;background:radial-gradient(closest-side,rgba(123,92,255,.25),transparent)}
  .npc img.pix,.npc-portrait.pix{object-fit:cover;object-position:50% 12%} .npc img.pix{background:rgba(123,92,255,.14)} .npc-portrait.pix{background:radial-gradient(closest-side,rgba(245,196,81,.18),rgba(4,8,21,.6))}
  .art-toggle{background:none;border:1px solid rgba(123,92,255,.45);border-radius:999px;padding:4px 10px;color:#d9ccff;font-size:12px}
  .lune.crop{width:100%;max-width:340px;border-radius:8px;box-shadow:0 0 30px rgba(180,156,255,.35)}
  .goddess.painted{grid-template-columns:1fr;justify-items:center} .goddess.painted .stack{width:100%}
  @media (max-width:520px){.npc-portrait{width:88px;height:88px}}
  .npc{display:flex;gap:12px;align-items:center;margin-bottom:8px} .npc img{width:72px;height:72px;border-radius:50%;object-fit:cover;flex:none;border:2px solid rgba(123,92,255,.6)}
  .npc .crop img{width:calc(var(--z) * 100%);height:auto;border:0;border-radius:0;max-width:none}
  .npc .voice{margin:0;text-align:left} .speech{font-style:italic;color:#ece6ff;margin:6px 0 0}
  .choice .npc + .offer{margin-top:4px}
  .gold-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;border:1px solid rgba(245,196,81,.5);background:rgba(245,196,81,.1);color:#ffe6a6;font-variant-numeric:tabular-nums}
  .gold-chip ha-icon{--mdc-icon-size:16px}
  button.chip{cursor:pointer;color:inherit;font:inherit;font-size:12px} button.chip.on{border-color:var(--gold);background:rgba(245,196,81,.18);color:#ffe6a6}
  /* market */
  .merchant-head{display:flex;gap:14px;align-items:center} .merchant-head p{margin:0 0 6px}
  .npc-portrait{width:120px;height:120px;border-radius:8px;object-fit:cover;flex:none;border:2px solid rgba(245,196,81,.5)}
  .npc-portrait.crop{height:auto;background:rgba(4,8,21,.6)} .npc-face{width:72px;flex:none;border-radius:50%;border:2px solid rgba(123,92,255,.6)}
  .cicon{width:56px;height:56px;display:grid;place-items:center;border-radius:6px;background:rgba(123,92,255,.12);border:1px solid rgba(123,92,255,.45);color:#d9ccff;flex:none}
  .cicon ha-icon{--mdc-icon-size:28px} .cicon.big{width:96px;height:96px}
  .cicon img.paint{image-rendering:auto;width:54px;height:54px;object-fit:cover;border-radius:5px}
  .wares{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr));gap:10px}
  .ware{display:flex;gap:12px;padding:10px;border:1px solid rgba(69,184,255,.25);border-radius:4px;background:rgba(69,184,255,.04)}
  .ware.on{border-color:var(--gold);box-shadow:0 0 12px rgba(245,196,81,.25)} .ware.sold{opacity:.45}
  .ware-body{display:grid;gap:3px;min-width:0} .price{font-variant-numeric:tabular-nums} .price b{color:#ffe6a6;font-size:16px} .price s{color:var(--dim)}
  .haggle{margin-top:12px;padding-top:12px;border-top:1px dashed rgba(245,196,81,.35);display:grid;gap:8px}
  .chatlog{display:grid;gap:6px;max-height:220px;overflow:auto;padding:4px 2px;align-content:start} .chatlog.tall{max-height:320px}
  .chatlog p{margin:0;padding:7px 10px;border-radius:10px;max-width:85%;font-size:13px}
  .chatlog .me{justify-self:end;background:rgba(69,184,255,.18);border:1px solid rgba(69,184,255,.35)}
  .chatlog .them{justify-self:start;background:rgba(123,92,255,.14);border:1px solid rgba(123,92,255,.35);color:#ece6ff}
  .chatlog .typing{opacity:.7;font-style:italic}
  form.row input{flex:1;min-width:0;background:rgba(4,8,21,.6);border:1px solid rgba(69,184,255,.45);border-radius:3px;padding:8px 10px;color:var(--ice);font:inherit}
  form.row input:focus-visible{outline:2px solid var(--gold);outline-offset:1px}
  .logrow{grid-column:2/4;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .logrow .btn{padding:4px 10px}
  .sleeplog{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;align-items:end;margin-top:12px;padding-top:10px;border-top:1px dashed rgba(69,184,255,.18)}
  .sleeplog b{grid-column:1/-1;font-weight:500} .sleeplog label{display:grid;gap:4px} .sleeplog input,.fixform input{background:rgba(4,8,21,.6);border:1px solid rgba(69,184,255,.45);border-radius:3px;color:var(--ice);padding:4px 6px;font:inherit;color-scheme:dark}
  .fed-up{padding:8px 10px;border:1px solid rgba(255,61,87,.6);background:rgba(255,61,87,.12);border-radius:3px;font-size:13px}
  .bagrow{display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px dashed rgba(123,92,255,.25)} .bagrow > div{flex:1}
  .cosrow{display:grid;gap:6px;margin-bottom:10px}
  .chron{padding:8px 0;border-bottom:1px dashed rgba(69,184,255,.2)} .chron p{margin:4px 0 0;font-style:italic;color:#ece6ff}
  .fixlink{background:none;border:0;padding:2px 0;color:var(--dim);cursor:pointer;justify-self:start;grid-column:2/-1;font:inherit;font-size:12px;text-decoration:underline dotted}
  .fixlink:hover,.fixlink:focus-visible{color:var(--ice)}
  .held{grid-column:1/-1;display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:#ffb3bf;margin-top:4px}
  .fixform{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:6px;padding:8px;border:1px dashed rgba(69,184,255,.35);border-radius:3px}
  .fixform label{display:grid;gap:3px} .fixform p{grid-column:1/-1;margin:0}
  .bounty{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px dashed rgba(245,196,81,.2)}
  .bounty.done{opacity:.55} .bh{margin:10px 0 2px;font-size:13px;font-weight:600;color:var(--gold)}
  .choreform{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;align-items:end;margin-top:10px;padding:8px;border:1px dashed rgba(245,196,81,.35);border-radius:3px}
  .choreform .wide{grid-column:1/-1} .choreform label{display:grid;gap:3px} .choreform label.check{display:flex;gap:6px;align-items:center}
  .choreform input:not([type=checkbox]),.choreform select{background:rgba(4,8,21,.6);border:1px solid rgba(245,196,81,.45);border-radius:3px;color:var(--ice);padding:4px 6px;font:inherit;color-scheme:dark}
  .you-row{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:16px;align-items:start}
  @media (max-width:700px){.you-row{grid-template-columns:minmax(0,1fr)}}
  .gallery.pair{grid-template-columns:repeat(auto-fill,minmax(min(100%,150px),1fr))}
  .prefs{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;align-items:end}
  .prefs label{display:grid;gap:4px} .prefs select{background:rgba(4,8,21,.6);border:1px solid rgba(69,184,255,.45);border-radius:3px;color:var(--ice);padding:5px 6px;font:inherit;color-scheme:dark}
  .prefs-go{grid-column:1/-1;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
  .prefs-go p,p.prefs-go{margin:0}
  .prefs.tiers{grid-template-columns:1fr;gap:10px} .tier{margin:0;padding:8px 10px 10px;border:1px solid rgba(69,184,255,.22);border-radius:4px;min-width:0}
  .tier legend{padding:0 6px;color:#bfe6ff} .tier.t-view legend{color:#9be8c0} .tier.t-edit legend{color:#ffe3a1} .tier.t-base legend{color:#ffc2ca}
  .tier p{margin:0 0 8px} .tierf{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;align-items:end}
  .gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,150px),1fr));gap:10px}
  .gtile{margin:0;min-width:0;display:grid;grid-template-columns:minmax(0,1fr);align-content:start;gap:6px;padding:6px;
    border:1px solid rgba(69,184,255,.2);border-radius:4px;background:rgba(4,8,21,.4)}
  .gtile.base{border-color:rgba(245,196,81,.5)}
  .gtile img,.gwait{display:block;width:100%;max-width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;border-radius:3px;background:rgba(123,92,255,.08)}
  .gtile.square img,.gtile.square .gwait{aspect-ratio:1/1}
  .gtile .crop{border-radius:3px;background:rgba(123,92,255,.08)} .gtile .crop img{aspect-ratio:auto;height:auto;object-fit:fill;border-radius:0;width:calc(var(--z) * 100%);max-width:none}
  .gwait{display:grid;place-items:center;color:var(--dim);font-size:12px;text-align:center;padding:6px}
  .gtile figcaption{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 6px;align-items:start;font-size:12px}
  .gtile .gname{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.35;overflow-wrap:break-word}
  .gtile figcaption .btn{padding:2px 6px}
  .gnote{grid-column:1/-1;color:var(--dim);font-size:11px;line-height:1.3}
  .sleeplog p{grid-column:1/-1;margin:0}
  .meters-note{margin:4px 0 0} .quiet{grid-column:1/-1;margin:4px 0 0}
  .odds span{white-space:nowrap} .odds .r-uncommon{color:#4fd18b} .odds .r-rare{color:#45b8ff} .odds .r-epic{color:#b072ff} .odds .r-legendary{color:#ffa640} .odds .r-mythic{color:#ff4d6d}
  .glitch{color:var(--dim)} .glitch span{color:#ff5a7a;font-family:ui-monospace,monospace;letter-spacing:.04em;display:inline-block;animation:glitch 2.6s steps(1) infinite}
  @keyframes glitch{0%,86%,100%{transform:none;opacity:1}88%{transform:translateX(-2px);opacity:.6}91%{transform:translateX(2px) skewX(-8deg)}94%{opacity:.3}}
  @media (prefers-reduced-motion:reduce){.glitch span,.stage img,.lair img,.toast,.burst,.rays,.reveal .chest .lid,.icon.r-mythic{animation:none}}
`;

// The full-screen panel only: page background, header, tabs and the responsive grid.
export const PANEL_CSS = `
  :host{min-height:100vh;background:radial-gradient(1200px 600px at 50% -10%,rgba(69,184,255,.18),transparent 60%),radial-gradient(800px 500px at 100% 100%,rgba(123,92,255,.14),transparent 60%),var(--abyss);
    overflow:auto;height:100vh}
  .page{max-width:1280px;margin:0 auto;padding:12px 16px 48px}
  ha-menu-button{color:var(--ice);--mdc-icon-button-size:40px;margin-left:-8px}
  header{display:flex;align-items:center;gap:16px;padding:6px 0 10px;flex-wrap:wrap}
  .brand{display:flex;align-items:center;gap:8px;letter-spacing:.3em;font-weight:600;color:#bfe6ff;text-shadow:0 0 10px rgba(69,184,255,.8)}
  .party{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
  .pchip{background:rgba(69,184,255,.08);border:1px solid rgba(69,184,255,.3);border-radius:999px;padding:4px 10px}
  .pchip.on{border-color:var(--gold);color:#ffe6a6} .pchip small{color:var(--dim)}
  nav{display:flex;flex-wrap:wrap;gap:2px 4px;border-bottom:1px solid rgba(69,184,255,.25);margin-bottom:16px}
  @media (max-width:600px){nav button{padding:8px 9px;font-size:13px}}
  .update-note{display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;margin:0 0 12px;padding:8px 12px;border:1px solid rgba(245,196,81,.55);border-radius:4px;background:rgba(245,196,81,.08);font-size:13px}
  nav button{background:none;border:0;border-bottom:2px solid transparent;padding:10px 12px;color:var(--dim);white-space:nowrap}
  nav button.on{color:#fff;border-bottom-color:var(--blue);text-shadow:0 0 8px rgba(69,184,255,.7)}
  .dot{display:inline-grid;place-items:center;min-width:16px;height:16px;padding:0 4px;border-radius:8px;background:var(--gold);color:#1a1200;font-style:normal;font-size:10px;font-weight:700}
  .dot.red{background:var(--red);min-width:8px;height:8px;padding:0} .dot.ok{background:#4fd18b}
  .cols{grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));align-items:start}
  @media (min-width:1180px){.st{grid-template-columns:minmax(0,1.7fr) minmax(0,1fr)}.tab-status .stage{width:256px!important}.tab-status .stage img.doll{width:256px;height:336px}.span2{grid-column:span 2}}
  @media (min-width:800px) and (max-width:1179px){.span2{grid-column:1/-1}}
  .center{min-height:70vh;display:grid;place-items:center;padding:16px}
  @media (max-width:520px){.status{grid-template-columns:1fr}.guardian,.goddess{grid-template-columns:1fr;justify-items:center}.goddess .lune.crop{max-width:260px}.lvl b{font-size:52px}
    .doll .stage{width:128px!important}.doll .stage img.doll{width:128px;height:168px}}
`;

// The dashboard cards only.
export const CARD_CSS = `
  ha-card{background:radial-gradient(500px 240px at 50% 0,rgba(69,184,255,.16),transparent 70%),var(--abyss);overflow:hidden;cursor:pointer}
  .body{padding:4px}.body .win{margin:4px}.body .grid{gap:8px}
  .lv{color:var(--dim)} .lv b{font-size:22px;font-weight:300;color:#fff} .rk{font-weight:700;margin-left:4px}
  .ell{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mini{display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:8px;font-size:12px}
  .mini span{display:block;color:var(--dim);margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis} .mini .done span{color:var(--gold)}
  .alert{margin-top:10px;padding:6px 8px;border:1px solid rgba(255,61,87,.6);background:rgba(255,61,87,.12);font-size:12px;border-radius:3px}
  .alert.violet-a{border-color:rgba(123,92,255,.6);background:rgba(123,92,255,.12)}
  .stage{padding-top:0;flex:none}
  .status{grid-template-columns:auto 1fr}
  .guardian{grid-template-columns:auto 1fr} .guardian .mon{width:144px;height:144px}
  @media (max-width:520px){.status,.guardian{grid-template-columns:1fr;justify-items:center}}
`;
