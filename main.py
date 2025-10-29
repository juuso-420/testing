# /// script
# dependencies = [
# "pygame"
# ]
# ///

# finance_tracker_pygbag_export_import.py
import pygame
import asyncio
import sys
from datetime import datetime, timedelta
import json
import os
import platform

pygame.init()

is_web = platform.system() == "Emscripten"

if is_web:
    import js

    async def mount_web_fs():
        """Mount /data to IDBFS and sync from browser storage before loading files."""
        if not js.FS.analyzePath("/data").exists:
            js.FS.mkdir("/data")
        js.FS.mount(js.IDBFS, {}, "/data")
        # Wait until IDBFS is synced into memory
        future = asyncio.get_event_loop().create_future()
        js.FS.syncfs(True, lambda err: future.set_result(None))
        await future
        os.chdir("/data")
        print("Web filesystem ready at /data")

    # Run the mounting/sync before starting main loop
    #asyncio.run(mount_web_fs())


#Helper to change screen rendering on web
import sys
WEB = False
if sys.platform in ["wasi", "emscripten"]:
    WEB = True
    from platform import window
    window.canvas.style.imageRendering = "pixelated"
print("WEB: ", WEB)


# Screen setup (resizable)
WIDTH, HEIGHT = 900, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Net Change Tracker")

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 200, 0)
RED = (200, 0, 0)
BLUE = (0, 0, 200)
GRAY = (220, 220, 220)
DARKGRAY = (80, 80, 80)
PINK_INPUT = (255, 0, 55)  # dark theme input color

is_dark_theme = False

font = pygame.font.SysFont(None, 24)

# Button config
BUTTON_HEIGHT = 30
BUTTON_WIDTH = 80
BUTTON_MARGIN = 10
THEME_BUTTON_WIDTH = 120
SIDE_BUTTON_WIDTH = 100  # width for Export / Import

buttons = []  # list of dicts {rect,label}

def setup_buttons():
    """Create buttons using current WIDTH (so resizable keeps them aligned)."""
    global buttons
    buttons = []
    x = BUTTON_MARGIN
    y = BUTTON_MARGIN
    left_labels = ["Day", "Week", "Month", "Year"]
    for label in left_labels:
        rect = pygame.Rect(x, y, BUTTON_WIDTH, BUTTON_HEIGHT)
        buttons.append({"rect": rect, "label": label})
        x += BUTTON_WIDTH + BUTTON_MARGIN

    # place right-side buttons: Dark Theme, Export, Import
    right_x = WIDTH - BUTTON_MARGIN - (THEME_BUTTON_WIDTH + SIDE_BUTTON_WIDTH*2 + BUTTON_MARGIN*2)
    rect = pygame.Rect(right_x, y, THEME_BUTTON_WIDTH, BUTTON_HEIGHT)
    buttons.append({"rect": rect, "label": "Dark Theme"})

    rect = pygame.Rect(right_x + THEME_BUTTON_WIDTH + BUTTON_MARGIN, y, SIDE_BUTTON_WIDTH, BUTTON_HEIGHT)
    buttons.append({"rect": rect, "label": "Export"})

    rect = pygame.Rect(right_x + THEME_BUTTON_WIDTH + BUTTON_MARGIN + SIDE_BUTTON_WIDTH + BUTTON_MARGIN, y, SIDE_BUTTON_WIDTH, BUTTON_HEIGHT)
    buttons.append({"rect": rect, "label": "Import"})

setup_buttons()

# Data storage (compact JSON format - B)
data_file = "finance_data.json"  # stored in /data when in web mode

# Data structure:
# data is dict keyed by date string "YYYY-MM-DD" -> {"entries":[{"type":"Earning"|"Spending","amount":absnum,"label":"...", "time":"HH:MM:SS"}]}
data = {}
if os.path.exists(data_file):
    try:
        # load compact format if present
        with open(data_file, "r") as f:
            raw = json.load(f)
        # handle two possibilities: earlier format (dict) or compact list
        if isinstance(raw, dict) and "entries" in raw:
            data = raw
        elif isinstance(raw, list):
            # convert compact list [[amt,label,date],[...]] to our dict form
            data = {}
            for item in raw:
                # each item expected [amount,label,YYYY-MM-DD] or [amount,label,datetime]
                amt = float(item[0])
                label = item[1] if len(item) > 1 else ""
                date_str = item[2] if len(item) > 2 else datetime.now().strftime("%Y-%m-%d")
                if date_str not in data:
                    data[date_str] = {"entries": []}
                t = datetime.now().strftime("%H:%M:%S")
                typ = "Earning" if amt >= 0 else "Spending"
                data[date_str]["entries"].append({"type": typ, "amount": abs(amt), "label": label, "time": t})
    except Exception:
        data = {}
else:
    data = {}

# Input + view mode
input_text = ""
view_mode = "Day"

# Hover/transactions trackers (previously referenced as globals but not defined)
hover_description = ""
transactions = []             # optional: can hold selected transactions if you expand features
current_hover_index = None

# ---------- Helper functions ----------
def save_data():
    """Save current data in compact JSON format and sync to IDBFS if web."""
    compact = []
    for date_str, val in data.items():
        for entry in val.get("entries", []):
            amt_signed = entry["amount"] if entry["type"]=="Earning" else -entry["amount"]
            compact.append([amt_signed, entry.get("label",""), date_str])
    try:
        with open(data_file, "w") as f:
            json.dump(compact, f)
    except Exception as e:
        print("Save error:", e)

    if is_web:
        try:
            future = asyncio.get_event_loop().create_future()
            js.FS.syncfs(False, lambda err: future.set_result(None))
            # Optional: await here if you want to make sure sync completes immediately
            # asyncio.get_event_loop().run_until_complete(future)
        except Exception as e:
            print("Web sync error:", e)

def load_data_from_file():
    """Load from existing compact JSON file into runtime `data` dict (safe)."""
    global data
    if not os.path.exists(data_file):
        data = {}
        return
    try:
        with open(data_file, "r") as f:
            raw = json.load(f)
        data = {}
        for item in raw:
            amt = float(item[0])
            label = item[1] if len(item) > 1 else ""
            date_str = item[2] if len(item) > 2 else datetime.now().strftime("%Y-%m-%d")
            t = datetime.now().strftime("%H:%M:%S")
            typ = "Earning" if amt >= 0 else "Spending"
            if date_str not in data:
                data[date_str] = {"entries": []}
            data[date_str]["entries"].append({"type": typ, "amount": abs(amt), "label": label, "time": t})
    except Exception as e:
        print("Load error:", e)
        data = {}

def add_entry(amount, label=""):
    today = get_today_str()
    if today not in data:
        data[today] = {"entries": []}
    type_ = "Earning" if amount >= 0 else "Spending"
    t = datetime.now().strftime("%H:%M:%S")
    data[today]["entries"].append({"type": type_, "amount": abs(amount), "label": label, "time": t})
    save_data()

def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")

def get_week_month_totals():
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    week_earn = week_spend = 0
    month_earn = month_spend = 0
    for date_str, val in data.items():
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        entries = val.get("entries", [])
        for entry in entries:
            if week_start <= date_obj <= today:
                if entry["type"] == "Earning":
                    week_earn += entry["amount"]
                else:
                    week_spend += entry["amount"]
            if month_start <= date_obj <= today:
                if entry["type"] == "Earning":
                    month_earn += entry["amount"]
                else:
                    month_spend += entry["amount"]
    return week_earn, week_spend, month_earn, month_spend

def get_view_data():
    today = datetime.now().date()
    view_data = []
    if view_mode == "Day":
        cumulative = 0
        entries_today = data.get(get_today_str(), {}).get("entries", [])
        for entry in entries_today:
            prev = cumulative
            if entry["type"] == "Earning":
                cumulative += entry["amount"]
                color = GREEN
            else:
                cumulative -= entry["amount"]
                color = RED
            view_data.append((prev, cumulative, color, entry["amount"], entry["type"], entry.get("label","")))
    elif view_mode == "Week":
        for i in range(7):
            day = today - timedelta(days=6-i)
            label = day.strftime("%d %b")
            entries_day = data.get(day.strftime("%Y-%m-%d"), {}).get("entries", [])
            earn = sum(e["amount"] for e in entries_day if e["type"]=="Earning")
            spend = sum(e["amount"] for e in entries_day if e["type"]=="Spending")
            net_change = earn - spend
            color = GREEN if net_change >= 0 else RED
            view_data.append((0, abs(net_change), color, label))
    elif view_mode == "Month":
        for i in range(30):
            day = today - timedelta(days=29-i)
            label = day.strftime("%d %b")
            entries_day = data.get(day.strftime("%Y-%m-%d"), {}).get("entries", [])
            earn = sum(e["amount"] for e in entries_day if e["type"]=="Earning")
            spend = sum(e["amount"] for e in entries_day if e["type"]=="Spending")
            net_change = earn - spend
            color = GREEN if net_change >= 0 else RED
            view_data.append((0, abs(net_change), color, label))
    elif view_mode == "Year":
        # 12 months for current year
        for i in range(12):
            # safe month creation even if today.month < i+1 by adjusting year if needed
            year = today.year
            month_idx = i + 1
            label = datetime(year, month_idx, 1).strftime("%b")
            month_earn = month_spend = 0
            for date_str, val in data.items():
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                except Exception:
                    continue
                if date_obj.year == year and date_obj.month == month_idx:
                    for entry in val.get("entries", []):
                        if entry["type"]=="Earning":
                            month_earn += entry["amount"]
                        else:
                            month_spend += entry["amount"]
            net_change = month_earn - month_spend
            color = GREEN if net_change >= 0 else RED
            view_data.append((0, abs(net_change), color, label))
    return view_data

# --- nice step function (for y-axis) ---
def nice_step(value):
    if value <= 10:
        return 1
    elif value <= 20:
        return 2
    elif value <= 50:
        return 5
    elif value <= 100:
        return 10
    elif value <= 200:
        return 20
    elif value <= 500:
        return 50
    elif value <= 1000:
        return 100
    else:
        step = 10 ** (len(str(int(value)))-1)
        return step

# ---------- Export / Import helpers ----------

def export_data_desktop():
    """Open save dialog and write compact JSON to chosen path (desktop)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")], title="Export finance data")
        root.destroy()
        if not path:
            return
        # write compact
        compact = []
        for date_str, val in data.items():
            for e in val.get("entries", []):
                amt_signed = e["amount"] if e["type"]=="Earning" else -e["amount"]
                compact.append([amt_signed, e.get("label",""), date_str])
        with open(path, "w") as f:
            json.dump(compact, f)
        print("Exported to", path)
    except Exception as e:
        print("Export failed:", e)

def import_data_desktop():
    """Open file dialog and load compact JSON (desktop)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")], title="Import finance data")
        root.destroy()
        if not path:
            return
        with open(path, "r") as f:
            raw = json.load(f)
        # write into local save file and reload
        with open(data_file, "w") as f:
            json.dump(raw, f)
        # if web, sync to IDB
        if is_web:
            js.FS.syncfs(False, lambda err: None)
        load_data_from_file()
        print("Imported from", path)
    except Exception as e:
        print("Import failed:", e)

def export_data_web():
    """Create a downloaded file in browser from current compact data (safe for localhost)."""
    try:
        import js
        if hasattr(js, "FS") and hasattr(js, "Blob"):
            # original export code here
            compact = []
            for date_str, val in data.items():
                for e in val.get("entries", []):
                    amt_signed = e["amount"] if e["type"]=="Earning" else -e["amount"]
                    compact.append([amt_signed, e.get("label",""), date_str])
            s = json.dumps(compact)
            b = js.Blob.new([s], {"type": "application/json"})
            url = js.URL.createObjectURL(b)
            a = js.document.createElement("a")
            a.href = url
            a.download = "finance_export.json"
            js.document.body.appendChild(a)
            a.click()
            a.remove()
            js.URL.revokeObjectURL(url)
        else:
            print("Web export skipped: js.FS not available (probably running locally).")
    except Exception as e:
        print("Web export failed:", e)

def import_data_web():
    """Open a file picker in browser, save selected file into /data, then sync."""
    try:
        import js
        if hasattr(js, "FS"):
            js_code = r"""
            (function(){
              var inp = document.createElement('input');
              inp.type = 'file';
              inp.accept = '.json';
              inp.onchange = function(e){
                var file = e.target.files[0];
                if(!file) return;
                var reader = new FileReader();
                reader.onload = function(ev){
                  var text = ev.target.result;
                  try {
                    FS.writeFile('/data/finance_data.json', text);
                    FS.syncfs(false, function(err){ console.log('imported to idbfs', err); });
                  } catch (err) { console.log('FS write error', err); }
                };
                reader.readAsText(file);
              };
              inp.click();
            })();
            """
            js.eval(js_code)
        else:
            print("Web import skipped: js.FS not available (probably running locally).")
    except Exception as e:
        print("Web import failed:", e)

# ---------- Drawing / UI ----------

def draw_buttons():
    for b in buttons:
        active = (b["label"] == view_mode) or (b["label"]=="Dark Theme" and is_dark_theme)
        color = BLUE if active else GRAY
        pygame.draw.rect(screen, color, b["rect"])
        pygame.draw.rect(screen, BLACK, b["rect"], 2)
        text_color = BLACK if not is_dark_theme else WHITE
        text_surf = font.render(b["label"], True, text_color)
        text_rect = text_surf.get_rect(center=b["rect"].center)
        screen.blit(text_surf, text_rect)

def draw_graph():
    bg_color = BLACK if is_dark_theme else WHITE
    grid_color = DARKGRAY if is_dark_theme else GRAY
    text_color = WHITE if is_dark_theme else BLACK

    screen.fill(bg_color)
    draw_buttons()

    y_offset = BUTTON_HEIGHT + BUTTON_MARGIN*2
    pygame.draw.line(screen, text_color, (50, 50 + y_offset), (50, HEIGHT-100), 2)
    pygame.draw.line(screen, text_color, (50, HEIGHT-100), (WIDTH-50, HEIGHT-100), 2)

    view_data = get_view_data()
    if not view_data:
        return

    # --- Determine scaling ---
    # Extract amounts for min/max cumulative range
    cumulative_vals = []
    cum = 0
    if view_mode == "Day":
        entries_today = data.get(get_today_str(), {}).get("entries", [])
        for entry in entries_today:
            val = entry["amount"] if entry["type"]=="Earning" else -entry["amount"]
            cum += val
            cumulative_vals.append(cum)
    else:
        cumulative_vals = [item[1] if item[2]==GREEN else -item[1] for item in view_data]

    max_val = max(cumulative_vals + [0])
    min_val = min(cumulative_vals + [0])
    net_range = max_val - min_val if max_val - min_val != 0 else 1
    x_scale = (WIDTH - 100) / len(view_data)
    y_scale = (HEIGHT - 150) / net_range

    zero_y = HEIGHT-100 - (0 - min_val)*y_scale

    # Horizontal grid
    step = nice_step(max(abs(max_val), abs(min_val)))
    grid_start = (min(min_val, 0)//step)*step
    grid_end   = ((max(max_val,0)//step)+1)*step
    i = grid_start
    while i <= grid_end:
        y = HEIGHT-100 - (i - min_val)*y_scale
        pygame.draw.line(screen, grid_color, (50, y), (WIDTH-50, y), 1)
        text = font.render(str(int(i)), True, text_color)
        screen.blit(text, (5, y-10))
        i += step

    pygame.draw.line(screen, grid_color, (50, zero_y), (WIDTH-50, zero_y), 2)

    # Draw bars
    bar_rects = []
    if view_mode == "Day":
        cum = 0
        for i, entry in enumerate(data.get(get_today_str(), {}).get("entries", [])):
            val = entry["amount"] if entry["type"]=="Earning" else -entry["amount"]
            color = GREEN if val >= 0 else RED
            prev_cum = cum
            cum += val
            top = zero_y - max(prev_cum, cum)*y_scale
            height = abs(val)*y_scale
            x = 50 + i*x_scale + x_scale*0.1
            rect = pygame.Rect(x, top, x_scale*0.8, height)
            pygame.draw.rect(screen, color, rect)
            bar_rects.append({"rect": rect, "amount": val, "label": entry.get("label",""), "color": color})
    else:
        # Week/Month/Year: keep original logic
        for i, item in enumerate(view_data):
            _, net_change, color, label = item
            val = net_change if color==GREEN else -net_change
            if val >= 0:
                top = zero_y - val*y_scale
                height = val*y_scale
            else:
                top = zero_y
                height = -val*y_scale
            x = 50 + i*x_scale + x_scale*0.1
            rect = pygame.Rect(x, top, x_scale*0.8, height)
            pygame.draw.rect(screen, color, rect)
            bar_rects.append({"rect": rect, "amount": val, "label": label, "color": color})

    # Tooltip logic unchanged
    mx, my = pygame.mouse.get_pos()
    for b in bar_rects:
        if b["rect"].collidepoint(mx, my):
            info_text = f"Value: {b['amount']}"
            if b.get("label"):
                info_text += f"\n{b['label']}"
            lines = info_text.split("\n")
            tooltip_width = max(font.size(line)[0] for line in lines) + 10
            tooltip_height = len(lines)*20 + 5
            tooltip_x = mx + 10 if mx + 10 + tooltip_width <= WIDTH else mx - tooltip_width - 10
            tooltip_y = my - tooltip_height - 10 if my - tooltip_height - 10 >= 0 else my + 10
            tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_width, tooltip_height)
            pygame.draw.rect(screen, GRAY, tooltip_rect)
            pygame.draw.rect(screen, BLACK, tooltip_rect, 2)
            for i, line in enumerate(lines):
                screen.blit(font.render(line, True, text_color), (tooltip_rect.x+5, tooltip_rect.y+5+i*20))
            break

def draw_input():
    text_color = PINK_INPUT if is_dark_theme else BLUE
    label = font.render(f"Enter amount (+optional note): {input_text}", True, text_color)
    screen.blit(label, (50, HEIGHT-50))

    today_entries = data.get(get_today_str(), {}).get("entries", [])
    net = sum(e["amount"] if e["type"]=="Earning" else -e["amount"] for e in today_entries)
    net_color = GREEN if net>=0 else RED

    week_earn, week_spend, month_earn, month_spend = get_week_month_totals()
    week_net = week_earn - week_spend
    month_net = month_earn - month_spend

    box_text = [
        f"Today: {get_today_str()}",
        f"Net: {net}",
        f"Week net: {week_net}",
        f"Month net: {month_net}"
    ]

    box_x = WIDTH - 200
    box_y = HEIGHT - 140
    bg_box = DARKGRAY if is_dark_theme else GRAY
    pygame.draw.rect(screen, bg_box, (box_x, box_y, 180, 130))
    pygame.draw.rect(screen, BLACK, (box_x, box_y, 180, 130), 2)
    for i, line in enumerate(box_text):
        if line.startswith("Net:"):
            color = net_color
        elif line.startswith("Week net:"):
            color = GREEN if week_net >= 0 else RED
        elif line.startswith("Month net:"):
            color = GREEN if month_net >= 0 else RED
        else:
            color = WHITE if is_dark_theme else BLACK
        screen.blit(font.render(line, True, color), (box_x + 10, box_y + 5 + i*20))

async def MAINLOOP():
    # ---------- Main loop ----------
    # passing global variables for the loop
    global is_dark_theme, view_mode, WIDTH, HEIGHT, screen
    global input_text, hover_description, transactions, current_hover_index
    global BLUE, GRAY  # we assign to BLUE & GRAY inside the loop so declare as global

    clock = pygame.time.Clock()

    # Ensure initial load from file (after possible web sync)
    load_data_from_file()

    while True:
        # theme color aliasing
        if is_dark_theme:
            BLUE = PINK_INPUT
            GRAY = DARKGRAY
        else:
            BLUE = (0, 0, 200)
            GRAY = (220, 220, 220)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_data()
                pygame.quit()
                sys.exit()

            if event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = event.w, event.h
                screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                # reposition buttons (dark/theme/export/import anchored to right)
                setup_buttons()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if input_text.strip():
                        try:
                            parts = input_text.strip().split(maxsplit=1)
                            value = float(parts[0])
                            label_text = parts[1] if len(parts)>1 else ""
                            add_entry(value, label_text)
                        except Exception:
                            pass
                    input_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                else:
                    # append event.unicode to global input_text
                    input_text += event.unicode

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for b in buttons:
                    if b["rect"].collidepoint(mx, my):
                        if b["label"] in ["Day", "Week", "Month", "Year"]:
                            view_mode = b["label"]
                        elif b["label"] == "Dark Theme":
                            is_dark_theme = not is_dark_theme
                        elif b["label"] == "Export":
                            if is_web:
                                export_data_web()
                            else:
                                export_data_desktop()
                        elif b["label"] == "Import":
                            if is_web:
                                import_data_web()
                                # after web import the FS is synced by JS; reload in-memory data:
                                load_data_from_file()
                            else:
                                import_data_desktop()
                        break

        draw_graph()
        draw_input()
        pygame.display.flip()
        clock.tick(30)

        await asyncio.sleep(0)

if __name__== "__main__":
    if is_web:
        asyncio.run(mount_web_fs())
    asyncio.run(MAINLOOP())
