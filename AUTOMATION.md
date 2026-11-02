# BMS Alert Report: daily automation

Daily flow, Monday to Saturday:

1. **8:30am**: EnTouch emails the "Active Alerts" CSV to mccoysfleet@gmail.com.
2. **9:00am Central**: a scheduled Claude task reads that email directly from the mccoysfleet Gmail inbox (connected to Claude), extracts the CSV, runs `build_report.py`, commits `index.html` and `mccoy_state.json` to this repo, and emails facilities_management@mccoys.com from mccoysfleet@gmail.com that the alerts are ready.
3. **Backup path (optional)**: if the task can't pull the attachment from Gmail, it checks the Drive folder "BMS System Alerts". The Apps Script below keeps a copy of each CSV there.

## Files in this repo

| File | Purpose |
|---|---|
| `index.html` | The dashboard (served by GitHub Pages). Contains all history baked in. |
| `mccoy_state.json` | Running state: dated snapshots, dispatched checkmarks, work-order notes. **This is the durable history.** |
| `tracker_template.html` | Dashboard template with all triage logic (`classify()`). No data inside. |
| `build_report.py` | CSV to state to `index.html`. Usage: `python3 build_report.py <csv> [<csv> ...]` |

Log a work order or finding (check the row off and attach a note):

```
python3 build_report.py --mark "<facility>|<device>|<alertType>" "<note>"
```

Add `--no-dispatch` to attach a note without checking the row off. For a combo unit, use the Zone Not Regulating row as the key.

## Step 2: Gmail to Drive (Google Apps Script)

Run this in the Gmail account that receives the EnTouch report (script.google.com, new project, paste, save, run `saveActiveAlerts` once to authorize, then add a time-driven trigger: every 10 minutes, or hourly between 8am and 9am).

```javascript
const FOLDER_ID = '1iCUzRyMWmCeE8fBJmzNPXCPW59ixVw6E';
const DONE_LABEL = 'BMS-Saved-To-Drive';

function saveActiveAlerts() {
  const folder = DriveApp.getFolderById(FOLDER_ID);
  const label = GmailApp.getUserLabelByName(DONE_LABEL) || GmailApp.createLabel(DONE_LABEL);
  const threads = GmailApp.search(
    'subject:"active alerts" has:attachment filename:csv newer_than:3d -label:' + DONE_LABEL
  );
  threads.forEach(thread => {
    thread.getMessages().forEach(msg => {
      msg.getAttachments().forEach(att => {
        if (/\.csv$/i.test(att.getName())) {
          const stamp = Utilities.formatDate(msg.getDate(), 'America/Chicago', 'yyyy-MM-dd_HHmm');
          folder.createFile(att.copyBlob().setName(stamp + '_' + att.getName()));
        }
      });
    });
    thread.addLabel(label);
  });
}
```

The script runs as whoever owns it, so the Drive folder must be writable by that account.

## Step 3: what the scheduled Claude task does

See the task prompt. In short: restore state from `mccoy_state.json`, run `build_report.py` on each new CSV, verify the page (script syntax, seed JSON, tab counts), push to `main`, send the notification email.
