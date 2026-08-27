const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, LevelFormat, ImageRun, TableOfContents,
        TabStopType } = require('docx');
const fs = require('fs');
const path = require('path');

const DARK = '004C8C';
const BLUE = '0096D6';
const LIGHT = 'EBF6FC';
const BORDER = 'D0DCE8';
const GRAY = 'F2F7FB';
const BODY = '333333';
const PAGE_W = 12240;
const PAGE_H = 15840;
const MARGIN = 1080; // 0.75"
const CONTENT = PAGE_W - MARGIN * 2; // 10080
const thin = { style: BorderStyle.SINGLE, size: 4, color: BORDER };
const borders = { top: thin, bottom: thin, left: thin, right: thin };
const noBorder = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

const logoPath = path.join(__dirname, '..', 'static', 'logo.png');
const logoData = fs.readFileSync(logoPath);
const logoW = 180;
const logoH = Math.round(logoW * (383 / 800));

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after ?? 160, before: opts.before ?? 0, line: 276 },
    alignment: opts.align,
    children: [new TextRun({
      text,
      font: 'Arial',
      size: opts.size || 22,
      color: opts.color || BODY,
      bold: !!opts.bold,
      italics: !!opts.italics,
    })],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: BLUE, space: 4 } },
    children: [new TextRun({ text, font: 'Arial', size: 32, bold: true, color: DARK })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, font: 'Arial', size: 26, bold: true, color: DARK })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, font: 'Arial', size: 22, bold: true, color: BLUE })],
  });
}

function bullets(items) {
  return items.map((text) => new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    spacing: { after: 80, line: 276 },
    children: [new TextRun({ text, font: 'Arial', size: 21, color: BODY })],
  }));
}

function cell(text, width, opts = {}) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: opts.fill || 'FFFFFF', type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({
        text,
        font: 'Arial',
        size: opts.size || 18,
        bold: !!opts.bold,
        color: opts.color || BODY,
      })],
    })],
  });
}

function twoCol(rows, c1 = 2800, c2 = CONTENT - 2800) {
  return new Table({
    width: { size: CONTENT, type: WidthType.DXA },
    columnWidths: [c1, c2],
    rows: [
      new TableRow({
        children: [
          cell('Module', c1, { bold: true, fill: DARK, color: 'FFFFFF' }),
          cell('What it is', c2, { bold: true, fill: DARK, color: 'FFFFFF' }),
        ],
      }),
      ...rows.map(([a, b], i) => new TableRow({
        children: [
          cell(a, c1, { bold: true, fill: i % 2 ? GRAY : LIGHT }),
          cell(b, c2, { fill: i % 2 ? GRAY : 'FFFFFF' }),
        ],
      })),
    ],
  });
}

const children = [];

children.push(new Paragraph({
  spacing: { after: 120 },
  children: [new ImageRun({
    type: 'png',
    data: logoData,
    transformation: { width: logoW, height: logoH },
    altText: { name: 'PPS logo', description: 'Pure Property Solutions wordmark', title: 'PPS' },
  })],
}));

children.push(new Paragraph({
  spacing: { after: 40 },
  children: [new TextRun({
    text: 'The PPS Hub',
    font: 'Arial', size: 48, bold: true, color: DARK,
  })],
}));
children.push(p('A field guide for the team', { size: 24, color: BLUE, after: 80 }));
children.push(p('From Thomas  ·  August 27, 2026  ·  hub.purepropsolutions.com', {
  size: 18, color: '666666', after: 280,
}));

children.push(p(
  'The Hub is where we actually do the work. Proposals, estimates, pipeline, training, clients. Bookmark it on your phone. Sign in with your own name — there is no shared password. This letter is the map.'
));
children.push(p(
  'You do not need every module. Use the ones that match your job. If something is missing or feels wrong, use the feedback box on the dashboard or tell me. Do not invent a workaround in a spreadsheet we already replaced.'
));

children.push(h1('How to get in'));
children.push(...bullets([
  'Open hub.purepropsolutions.com. Pick your name. Use the password you set. Forgot Password emails a one-hour reset link.',
  'Sessions last 30 days of idle time. You should not have to log in every morning. If you get bounced to login, use Forgot Password — do not text someone else for theirs.',
  'On your phone: open it in Safari or Chrome, then Add to Home Screen. That icon is the Hub, not a browser bookmark. It works offline enough to tell you the Hub is unreachable.',
  'Nobody shares an account. If someone leaves, we take their name off the roster and their session dies. That only works if you never loaned them your login.',
]));

children.push(h1('What it is for'));
children.push(p(
  'PPS used to live in inboxes, side chats, and whoever had the latest Excel. The Hub is the source of truth for the work we produce: which proposal went out, which estimate we ran, which row is sitting on a board, who finished training. Monday morning you get a recap of last week so the whole company can see who is producing. Page opens do not count. Completing work does.'
));
children.push(p(
  'The dashboard is a launcher, not a second job. Jump back in takes you to the last three tools you actually used. The pills at the top are this week’s score, open pipeline, and unfinished training. A zero does not show. Quiet week, short dashboard.'
));

children.push(h1('At a glance'));
children.push(twoCol([
  ['Dashboard', 'Your week, jump-back cards, and every tool in two lanes (Sales and Production).'],
  ['Proposal Generator', 'Opens the proposal tool. Client-facing language, branded Word docs.'],
  ['Proposal History', 'Find, download, or regenerate a proposal you already made.'],
  ['Clients', 'Shared contact list. Search instead of retyping a name.'],
  ['Ask PPS', 'Ask a PPS question. Curated answers, not a random chatbot.'],
  ['Pipeline Board', 'Live consultant/PM tracker. One board per consultant. 3-second refresh.'],
  ['Estimating', 'Siding, roofing, gutter, painting takeoffs. Excel out. Yellow cells still edit.'],
  ['Site Visit', 'Field notes and photos after a walk.'],
  ['PPM Checklist', 'Pre-project meeting from an approved proposal.'],
  ['Trade Partner Scope', 'Crew-ready scope, English and Spanish.'],
  ['PSC / PM Training', 'Onboarding. Oversight is leadership. Week 5 of PM training is not built yet.'],
  ['Team View', 'Same scoring as Monday’s email, for the last twelve weeks.'],
  ['Office Ops', 'Numbers pack and Trade Partner insurance. Leadership only.'],
  ['Pricing Defaults', 'Company rates that pre-fill estimators. Leadership can edit (new).'],
]));

children.push(new Paragraph({
  spacing: { before: 240, after: 80 },
  children: [new TextRun({ text: 'Contents', font: 'Arial', size: 26, bold: true, color: DARK })],
}));
children.push(new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-2' }));

children.push(h1('Dashboard'));
children.push(p(
  'This is home. Sales & Consulting on top, Production below. On a phone the lanes fold; that is remembered. A brand-new hire with no history keeps both lanes open so they are not staring at grey bars.'
));
children.push(h3('Jump back in'));
children.push(p(
  'Three cards, most recent first — not “most used this month.” History is not permission: if you lost access to a tool, it will not hand you a card that bounces you. Pipeline Board is picky for me because I have no default board; yours opens the one you last used, then your default.'
));
children.push(h3('Ask PPS and feedback'));
children.push(p(
  'Both sit in fold-down blocks on the dashboard. Ask PPS is for “how do we do X at PPS.” Feedback is for “the Hub should do Y.” Feedback comes to me. Ask PPS answers from our voice, training, and pricing notes — it is not allowed to invent a number as policy.'
));

children.push(h1('Sales & consulting'));
children.push(h2('Proposal Generator'));
children.push(p(
  'Opens the proposal tool in a new window, already signed in. Use it for client proposals, not for notes to yourself. It writes in PPS language: residents, not tenants; apartment community, not complex; Trade Partners, not subcontractors; investment, not price, on the total. You still own the walk-through and the number. If a photo comes out sideways, that was a phone-orientation bug — it is fixed. Tell me if it happens again.'
));
children.push(...bullets([
  'Pick the consultant the book belongs to. If you are writing for someone else, credit still follows whoever generated it.',
  'Site photos: take them upright. The tool now rotates them the right way.',
  'When you finish, it lands in Proposal History automatically.',
]));

children.push(h2('Proposal History'));
children.push(p(
  'Search what you have already produced. Consultants see their book. PMs see their own plus paired consultants. Download the Word file or regenerate. Client, contact, and company show on the detail when we have them — older rows logged before the vault path will be blank. That is not a bug. Do not print “Contact —” on those.'
));

children.push(h2('Clients'));
children.push(p(
  'Shared contact list for proposals and pipeline. Search by name, email, or company. Add a contact once. Monday CRM syncs new contacts weekly (insert-only — it will not overwrite a Hub-only contact). Placeholder names like “New Contact” are skipped. Use this instead of a personal spreadsheet.'
));

children.push(h2('Ask PPS'));
children.push(p(
  'Type a real question. “How do we handle a concealed condition on a condo?” is a good one. “Write me a proposal” is not — that is the Proposal Generator. Leadership curates answers. If you are assigned a prompt (a gap we know we have), answer it. That is how the library grows. Do not paste salaries, appraisals, or anyone’s performance notes in here. That stays out of the Hub on purpose.'
));

children.push(h2('PSC Training'));
children.push(p(
  'Twelve-week onboarding for consultants: trades, shadowing, PPS voice, sales. You only see it if you are enrolled. Check off items as you finish them. A week that is signed off stays signed off — new material added later shows at the bottom as “Added since you started” and does not reopen a finished week. Roleplay is a separate page for enrolled PSCs. Tony, Trey, and Stephanie enroll people and sign weeks off. Only I can revoke a sign-off.'
));

children.push(h1('Production'));
children.push(h2('Pipeline Board'));
children.push(p(
  'One live board per consultant. You and your PM (and anyone else on the team) see the same rows. Statuses include new, needs walk/scope, scoped, then the later ones. Yellow means in-progress, not Sent/Awarded/Cancelled. New rows start at new. It polls every 3 seconds. That is on purpose — we are not putting the whole Hub on one chat socket again.'
));
children.push(...bullets([
  'Search: the box in the toolbar, or press / (not while you are inside a cell). Terms AND together. “Walk” matches the status “Needs walk/scope.” Escape or the X clears it. Hidden rows stay in the page so a refresh does not dump them back in the wrong order.',
  'Jump to open work: first open row you can still see.',
  'Client Contact is the client’s manager, not the PPS PM. It suggests last-used names on that property.',
  'Adding a row while a search is running clears the search so you are not creating an invisible row.',
  'Import from Excel is leadership-only. Editing and archiving a row is open to the whole roster. Import rewrites a board; editing moves one row.',
  'If the board ever looks empty, do not panic and do not keep refreshing until it “comes back.” A failed load keeps the last rows. Tell me.',
]));

children.push(h2('Estimating'));
children.push(p(
  'Four tools under one roof. Upload the measurement PDF you already buy (EagleView, Roofr, Bid Perfect) or type field numbers. You get a takeoff, a number, and an Excel file. Yellow cells in Excel stay editable. Company rates pre-fill from Pricing Defaults. You can still change a number on that job. Changing the company default is leadership, not a yellow cell.'
));
children.push(h3('Siding'));
children.push(p(
  'One takeoff per building type (A/B/C/D) and how many of that type. Stack is Cost (labor + haul + delivery) + Markup $ + Overhead $ = Invoice. Margin % is Markup / Invoice. Those numbers write into Excel Tab 6 — you should not be typing yellow zeros after download. Types and quantities roll up on the result page.'
));
children.push(h3('Roofing'));
children.push(p(
  'GAF material list from a Premium or Roofr report, or a quick bid from EagleView Bid Perfect. Labor per square, material, tax, waste, dump loads. Same rule: override the job, do not silently rewrite company defaults.'
));
children.push(h3('Gutters'));
children.push(p(
  'Eaves length in, gutters / downspouts / guards out. Spacing and downspout height are defaults you can change on the job. Good for a same-day number when the roof report is already in hand.'
));
children.push(h3('Exterior painting'));
children.push(p(
  'Field takeoff by category. Labor hours from production rates, paint, one-coat and two-coat bids. If the rate looks wrong, tell Trey or Tony — they can fix the company default now.'
));

children.push(h2('Site Visit Report'));
children.push(p(
  'Use it after a walk, not instead of a walk. Photos, notes, what you saw versus what was proposed. This is the record when someone asks three weeks later what was on the building.'
));

children.push(h2('Pre-Project Meeting (PPM)'));
children.push(p(
  'Checklist generated from an approved proposal. This is the handoff between sales and production. If you skip it, the job still starts — it just starts with gaps. History is under My PPMs.'
));

children.push(h2('Trade Partner Scope (TPS)'));
children.push(p(
  'Crew-ready scope from the proposal, English and Spanish. This is what we send the Trade Partner, not a paste from the client proposal. History: My TPS Scopes. PMs and consultants who generated one, or who are PM on it, can find it there.'
));

children.push(h2('PM Training'));
children.push(p(
  'Four weeks are live: Production Board, routes, Trade Partners, materials/callbacks. Week 5 (scoreboard / production-meeting cadence) is designed and not built yet — do not wait on it. Same enrollment rules as PSC: leadership enrolls and signs off. Added items after you started sit at the bottom and do not undo a signed week.'
));

children.push(h1('Team View'));
children.push(p(
  'Open to everyone. Same scoring as the Monday recap: this week plus a rolling twelve. Ranked inside Consultants / PMs / Office, not one flat list. Credit follows whoever generated the work, not whose name is on the proposal. Pipeline and Hub actions are capped so a week of real deliverables still leads. If your number disagrees with Monday’s email, that is a bug — tell me. Do not keep a second spreadsheet of “my real number.”'
));

children.push(h1('Monday recap'));
children.push(p(
  'Every Monday around 7am Eastern you get an email with last week’s board. Your row is highlighted. A visible 0 is better than a missing name. Opens do not score. I am on the board with you. If the email does not arrive, it is not because you were left off — tell me so we can see if the job ran.'
));

children.push(h1('Leadership only'));
children.push(p(
  'Stephanie, Tony, and Trey (and me). If that is not you, skip this section.'
));
children.push(h2('Office Ops'));
children.push(p(
  'Two cards: Numbers and Compliance. Numbers is the Thursday pack from QuickBooks — Invoice List / Rep Sales YTD and AR aging. Stephanie uploads the Excel as-is (filename “Rep Sales YTD” is fine). Compliance is Trade Partner insurance: expired, expiring, new, and pay-request mismatches. View COI opens the file. Date overrides beat a stale Monday board date and lose to a COI we can actually read. “Run now” sends a real email. Do not click it to see what it looks like.'
));
children.push(h2('Training oversight and editor'));
children.push(p(
  'Enroll, sign weeks, read feedback. Edit Training is the curriculum editor. Drafts are invisible to trainees until you Publish. A published add shows in-week for new hires and in “Added since you started” for people already enrolled. Do not insert an item in the middle of a list in the Python files — that is how checkmarks silently move. Use the editor. Discard only works on never-published drafts. Hide live items instead of deleting them.'
));
children.push(h2('Estimating pricing defaults (new)'));
children.push(p(
  'You can now edit the company rates that pre-fill siding, roofing, gutter, and painting. Dashboard → Production → Estimating Pricing Defaults, or Estimating → Company Pricing Defaults. Save writes for the whole team. A field person can still change a number on one job. They cannot change what the next job starts with.'
));
children.push(...bullets([
  'If a trade’s labor or material moved, change it here the same day. Do not wait on me.',
  'Excel yellow cells remain the per-job override. Do not tell the team to “just edit Excel” as the new default.',
  'The last-updated line is Eastern time and shows who saved.',
]));

children.push(h1('What not to do'));
children.push(...bullets([
  'Do not share a login. Ever.',
  'Do not score yourself by opening pages. The recap ignores that on purpose.',
  'Do not put salaries, appraisals, or “who we might let go” in Ask PPS or a training note.',
  'Do not import a spreadsheet onto a Pipeline Board unless you are leadership — and even then, only when a new consultant is starting from Excel.',
  'Do not rebuild a personal tracker for something the Hub already stores.',
  'Do not call Office Ops “the admin page.” Admin is mine. Office Ops is Numbers and Compliance.',
]));

children.push(h1('If it is broken'));
children.push(p(
  'Feedback box on the dashboard, or text me. Include which page and what you clicked. “It froze” on a proposal usually meant the detail modal — that close-button bug is fixed. Pipeline looking empty is a load failure, not a wipe. Estimating numbers that look like last year’s rates probably mean the default was not updated — leadership can fix that now.'
));
children.push(p(
  'Thomas', { before: 240, after: 0, bold: true }
));
children.push(p(
  'hub.purepropsolutions.com', { size: 18, color: BLUE, after: 0 }
));

const doc = new Document({
  styles: {
    default: { document: { run: { font: 'Arial', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 32, bold: true, font: 'Arial', color: DARK },
        paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 26, bold: true, font: 'Arial', color: DARK },
        paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 22, bold: true, font: 'Arial', color: BLUE },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [{
      reference: 'bullets',
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: '•',
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: PAGE_H },
        margin: { top: MARGIN, right: MARGIN, bottom: 1260, left: MARGIN },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          tabStops: [{ type: TabStopType.RIGHT, position: CONTENT }],
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: BLUE, space: 6 } },
          spacing: { after: 120 },
          children: [
            new TextRun({ text: 'Pure Property Solutions', font: 'Arial', size: 16, color: DARK, bold: true }),
            new TextRun({ text: '\tHub field guide  ·  August 2026', font: 'Arial', size: 16, color: '888888' }),
          ],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          tabStops: [{ type: TabStopType.RIGHT, position: CONTENT }],
          border: { top: { style: BorderStyle.SINGLE, size: 6, color: BORDER, space: 6 } },
          spacing: { before: 80 },
          children: [
            new TextRun({ text: 'Internal — PPS team', font: 'Arial', size: 16, color: '888888' }),
            new TextRun({ text: '\tPage ', font: 'Arial', size: 16, color: '888888' }),
            new TextRun({ children: [PageNumber.CURRENT], font: 'Arial', size: 16, color: '888888' }),
          ],
        })],
      }),
    },
    children,
  }],
});

const outDir = process.argv[2];
if (!outDir) {
  console.error('usage: node generate_hub_intro_docx.js <output-dir>');
  process.exit(1);
}
const out = path.join(outDir, 'PPS_Hub_Introduction.docx');
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log('wrote', out, buf.length);
});
