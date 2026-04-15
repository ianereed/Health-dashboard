---
description: Process MyHealth Online screenshots into structured medical records and update calendar/reminders as needed
argument-hint: [path/to/screenshot.png ...]
---

The user wants to process one or more MyHealth Online screenshots into structured medical records.

Arguments (screenshot paths): $ARGUMENTS

Steps:
1. If $ARGUMENTS is empty, look for loose `.png` files in `medical-records/` or that the user has mentioned in this session. Ask the user to confirm which files to process if it's ambiguous.
2. Run the processing script:
   ```
   python3 /Users/ianreed/Documents/GitHub/Home-Tools/medical-records/process_screenshots.py <paths>
   ```
3. Read the output file that was saved and summarize what was extracted — highlight any new appointments, changed times, action items, or insurance notes.
4. For any NEW appointments not already on the calendar, offer to create them on Google Calendar using the pattern in `medical-records/create_calendar_events.py`.
5. For any appointment changes (reschedules, cancellations), offer to update or delete the existing calendar event.
6. For any action items (call to reschedule, pay a bill, get auth renewed), offer to add a Reminders entry.

Always confirm before writing to calendar or Reminders.
