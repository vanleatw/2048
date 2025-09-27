# 2048 — Smooth & Satisfying (Pygame, phone-friendly, swipe support)
# Works on desktop AND as a web app via pygbag + GitHub Pages.

import pygame as pg
import random, math, sys

# --------------------------
# Settings / Theme
# --------------------------
BOARD_N = 4
FPS = 60
BG = (250, 248, 239)
BOARD_BG = (187, 173, 160)
EMPTY = (205, 193, 180)
FONT_NAME = None  # default system font

TILE_COLORS = {
    2:(238,228,218),(119,110,101),
    4:(237,224,200),(119,110,101),
    8:(242,177,121),(249,246,242),
    16:(245,149, 99),(249,246,242),
    32:(246,124, 95),(249,246,242),
    64:(246, 94, 59),(249,246,242),
    128:(237,207,114),(249,246,242),
    256:(237,204, 97),(249,246,242),
    512:(237,200, 80),(249,246,242),
    1024:(237,197, 63),(249,246,242),
    2048:(237,194, 46),(249,246,242),
}

# --------------------------
# Helpers
# --------------------------
def lerp(a,b,t): return a + (b-a)*t
def ease_out_cubic(t): return 1 - (1-t)**3
def ease_in_out_quad(t): return 2*t*t if t<0.5 else 1 - (-2*t+2)**2/2
def clamp(v,lo,hi): return max(lo,min(hi,v))

def make_font(px, bold=False):
    return pg.font.SysFont(FONT_NAME, px, bold=bold)

def rounded_rect(surface, color, rect, radius=12):
    x,y,w,h = rect
    pg.draw.rect(surface,color,(x+radius,y,w-2*radius,h))
    pg.draw.rect(surface,color,(x,y+radius,w,h-2*radius))
    pg.draw.circle(surface,color,(x+radius,y+radius),radius)
    pg.draw.circle(surface,color,(x+w-radius,y+radius),radius)
    pg.draw.circle(surface,color,(x+radius,y+h-radius),radius)
    pg.draw.circle(surface,color,(x+w-radius,y+h-radius),radius)

# --------------------------
# Layout
# --------------------------
def calc_layout(size_wh, n=BOARD_N):
    W,H = size_wh
    pad_top = 90  # room for scoreboard
    size = int(min(W, H - pad_top) * 0.95)
    gap = max(8, size // (n*14))
    cell = (size - (n+1)*gap)//n
    size = n*cell + (n+1)*gap
    x0 = (W - size)//2
    y0 = (H - pad_top - size)//2 + pad_top
    return x0,y0,size,cell,gap,pad_top

def font_for_value(val, cell):
    digits = len(str(val))
    base = {1:.58,2:.52,3:.46}.get(digits,.40)
    return make_font(max(14,int(cell*base)), bold=True)

def color_for_value(val):
    if val in TILE_COLORS:
        c = TILE_COLORS[val]
        return c[0], c[1]
    # beyond 2048: keep hue, darken
    k = max(46, 194 - int(math.log(val,2)-11)*12)
    return (237,k,46),(249,246,242)

# --------------------------
# Game State & Tile Objects
# --------------------------
class Tile:
    __slots__ = ("row","col","val","px","py","tx","ty","scale","merge_timer","glow","dead")
    def __init__(self, r,c,val, px,py):
        self.row,self.col,self.val = r,c,val
        self.px,self.py = px,py     # pixel position (animated)
        self.tx,self.ty = px,py     # target pixel pos
        self.scale = 1.0            # 1.0 normal; >1 pop
        self.merge_timer = 0.0      # small flash duration
        self.glow = 0.0             # gentle outer glow
        self.dead = False           # marked for removal (merged into another)

class Game:
    def __init__(self, screen):
        self.screen = screen
        self.W,self.H = self.screen.get_size()
        self.reset()

    def reset(self):
        self.score = 0
        self.best = 0
        self.game_over = False
        self.tiles = []   # list[Tile]
        self.grid = [[None]*BOARD_N for _ in range(BOARD_N)]
        self.relayout()
        self.spawn(); self.spawn()

    def relayout(self):
        self.x0,self.y0,self.size,self.cell,self.gap,self.pad_top = calc_layout((self.W,self.H))
        # recompute pixel targets for all tiles to keep them aligned if window changes
        for t in self.tiles:
            t.tx,t.ty = self.cell_pos_px(t.row,t.col)
            # do not snap; let anim interpolate

    def cell_pos_px(self, r,c):
        x = self.x0 + self.gap + c*(self.cell+self.gap)
        y = self.y0 + self.gap + r*(self.cell+self.gap)
        return x,y

    def empty_cells(self):
        out=[]
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                if self.grid[r][c] is None:
                    out.append((r,c))
        return out

    def spawn(self):
        empties = self.empty_cells()
        if not empties: return
        r,c = random.choice(empties)
        val = 4 if random.random()<0.1 else 2
        x,y = self.cell_pos_px(r,c)
        t = Tile(r,c,val,x,y)
        t.scale = 0.2         # spawn pop-in
        t.glow = 0.8
        self.grid[r][c] = t
        self.tiles.append(t)

    def can_move(self):
        if self.empty_cells(): return True
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                a = self.grid[r][c].val
                if r+1<BOARD_N and self.grid[r+1][c].val==a: return True
                if c+1<BOARD_N and self.grid[r][c+1].val==a: return True
        return False

    # Core move with animation plan
    def move(self, direction):
        if self.game_over: return False
        moved = False
        n = BOARD_N

        # Helpers to rotate views so we always "move left"
        def read_rows():
            if direction=='L':
                return [[self.grid[r][c] for c in range(n)] for r in range(n)]
            if direction=='R':
                return [[self.grid[r][n-1-c] for c in range(n)] for r in range(n)]
            if direction=='U':
                return [[self.grid[c][r] for c in range(n)] for r in range(n)]
            if direction=='D':
                return [[self.grid[n-1-c][r] for c in range(n)] for r in range(n)]

        def write_rows(rows):
            if direction=='L':
                for r in range(n):
                    for c in range(n): self.grid[r][c]=rows[r][c]
            if direction=='R':
                for r in range(n):
                    for c in range(n): self.grid[r][n-1-c]=rows[r][c]
            if direction=='U':
                for r in range(n):
                    for c in range(n): self.grid[c][r]=rows[r][c]
            if direction=='D':
                for r in range(n):
                    for c in range(n): self.grid[n-1-c][r]=rows[r][c]

        rows = read_rows()
        gained = 0
        travel_time = 0.12  # seconds for slide
        now_moves = []

        for r in range(n):
            line = [t for t in rows[r] if t is not None and not t.dead]
            # compress + merge left
            out=[]
            i=0
            while i < len(line):
                if i+1 < len(line) and line[i].val == line[i+1].val:
                    a,b = line[i], line[i+1]
                    # merge b into a
                    new_val = a.val*2
                    a.val = new_val
                    a.merge_timer = 0.18
                    a.scale = 1.2
                    a.glow = 1.0
                    b.dead = True
                    gained += new_val
                    out.append(a)
                    i += 2
                else:
                    out.append(line[i]); i += 1
            out += [None]*(n - len(out))
            # record new positions and animation targets
            for c in range(n):
                t = out[c]
                if t is not None:
                    # find original column in this rotated view
                    if t.col is None: pass
                    # compute world coords for rotated view
                    if direction in ('L','R'):
                        new_r,new_c = (r, c if direction=='L' else (n-1-c))
                    else: # U,D
                        new_r,new_c = (c if direction=='U' else (n-1-c), r)
                    # move tile to new cell
                    if (t.row,t.col) != (new_r,new_c):
                        moved = True
                    t.row,t.col = new_r,new_c
                    tx,ty = self.cell_pos_px(new_r,new_c)
                    t.tx,t.ty = tx,ty
                    now_moves.append((t, travel_time))
            rows[r] = out

        # replace grid with merged rows (un-rotated by write_rows)
        write_rows(rows)

        # remove dead (merged-into) tiles AFTER writing grid
        if any(t.dead for t in self.tiles):
            self.tiles = [t for t in self.tiles if not t.dead]

        if moved:
            self.score += gained
            self.best = max(self.best, self.score)
            self.spawn()
            if not self.can_move():
                self.game_over = True
        return moved

    # ----------------------
    # Update & Draw
    # ----------------------
    def update(self, dt):
        # animate positions, pop & glow
        speed = clamp(dt*1.0, 0.0, 1.0)
        for t in self.tiles:
            # slide
            t.px = lerp(t.px, t.tx, ease_in_out_quad(clamp(speed*8,0,1)))
            t.py = lerp(t.py, t.ty, ease_in_out_quad(clamp(speed*8,0,1)))
            # spawn/merge pop decay
            t.scale = lerp(t.scale, 1.0, clamp(dt*10,0,1))
            # glow decay
            t.glow = max(0.0, t.glow - dt*1.6)
            # merge flash timer
            if t.merge_timer>0:
                t.merge_timer = max(0.0, t.merge_timer - dt)

    def draw(self):
        S = self.screen
        S.fill(BG)

        # Header / score
        self.draw_header(S)

        # Board
        rounded_rect(S, BOARD_BG, (self.x0, self.y0, self.size, self.size), 14)

        # Cells background
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                x = self.x0 + self.gap + c*(self.cell+self.gap)
                y = self.y0 + self.gap + r*(self.cell+self.gap)
                rounded_rect(S, EMPTY, (x,y,self.cell,self.cell), 10)

        # Tiles with glow & pop
        for t in sorted(self.tiles, key=lambda k: k.val):  # small to big
            bg, fg = color_for_value(t.val)
            # glow layer
            if t.glow>0:
                glow = pg.Surface((self.cell,self.cell), pg.SRCALPHA)
                g = int(90*t.glow)
                pg.draw.ellipse(glow, (0,0,0,g), glow.get_rect())
                S.blit(glow, glow.get_rect(center=(t.px+self.cell/2, t.py+self.cell/2)))
            # pop scale
            scale = clamp(t.scale, 0.15, 1.25)
            w = int(self.cell*scale); h = int(self.cell*scale)
            x = int(t.px + (self.cell - w)/2)
            y = int(t.py + (self.cell - h)/2)
            rounded_rect(S, bg, (x,y,w,h), max(6,int(10*scale)))
            # merge flash overlay
            if t.merge_timer>0:
                alpha = int(180*ease_out_cubic(t.merge_timer/0.18))
                overlay = pg.Surface((w,h), pg.SRCALPHA)
                pg.draw.rect(overlay,(255,255,255,alpha),overlay.get_rect(), border_radius=max(6,int(10*scale)))
                S.blit(overlay,(x,y))
            # value text
            txt = font_for_value(t.val, self.cell).render(str(t.val), True, fg)
            S.blit(txt, txt.get_rect(center=(x+w/2, y+h/2)))

        if self.game_over:
            self.draw_game_over(S)

    def draw_header(self, S):
        # Title
        title = make_font(42, True).render("2048", True, (119,110,101))
        S.blit(title, (self.x0, self.y0 - 64))
        # Score boxes
        box_w, box_h = 110, 54
        gap = 12
        xR = self.x0 + self.size - (box_w*2 + gap)
        y = self.y0 - 72
        for label, val, ox in (("SCORE", self.score, 0), ("BEST", self.best, box_w+gap)):
            rect = (xR+ox, y, box_w, box_h)
            rounded_rect(S, (187,173,160), rect, 10)
            rounded_rect(S, (205,193,180), (xR+ox+2,y+2,box_w-4,box_h-4), 9)
            f1 = make_font(14, True).render(label, True, (119,110,101))
            f2 = make_font(20, True).render(str(val), True, (86,80,70))
            S.blit(f1, (xR+ox + (box_w - f1.get_width())/2, y+6))
            S.blit(f2, (xR+ox + (box_w - f2.get_width())/2, y+28))

    def draw_game_over(self, S):
        overlay = pg.Surface((self.W,self.H), pg.SRCALPHA)
        overlay.fill((0,0,0,140))
        S.blit(overlay,(0,0))
        t1 = make_font(64, True).render("Game Over", True, (255,255,255))
        t2 = make_font(26).render("Swipe or Arrow Keys to try again (R to reset)", True, (240,240,240))
        S.blit(t1, t1.get_rect(center=(self.W/2, self.H/2 - 18)))
        S.blit(t2, t2.get_rect(center=(self.W/2, self.H/2 + 22)))

# --------------------------
# Input: keys + swipe
# --------------------------
def direction_from_swipe(start, end, thresh=24):
    dx, dy = end[0]-start[0], end[1]-start[1]
    if abs(dx)<thresh and abs(dy)<thresh: return None
    return ('R' if dx>0 else 'L') if abs(dx)>abs(dy) else ('D' if dy>0 else 'U')

# --------------------------
# Main
# --------------------------
def main():
    pg.init()
    pg.display.set_caption("2048 — Smooth & Satisfying")
    screen = pg.display.set_mode((640, 900), pg.RESIZABLE)
    clock = pg.time.Clock()
    g = Game(screen)
    swipe_start = None

    while True:
        dt = clock.tick(FPS)/1000.0
        for e in pg.event.get():
            if e.type == pg.QUIT:
                pg.quit(); sys.exit()
            elif e.type == pg.VIDEORESIZE:
                screen = pg.display.set_mode((e.w, e.h), pg.RESIZABLE)
                g.screen = screen
                g.W,g.H = e.w,e.h
                g.relayout()
            elif e.type == pg.KEYDOWN:
                if e.key == pg.K_r:
                    g.reset()
                elif not g.game_over:
                    keymap = {
                        pg.K_LEFT:'L', pg.K_a:'L',
                        pg.K_RIGHT:'R', pg.K_d:'R',
                        pg.K_UP:'U', pg.K_w:'U',
                        pg.K_DOWN:'D', pg.K_s:'D'
                    }
                    d = keymap.get(e.key)
                    if d: g.move(d)
                else:
                    if e.key in (pg.K_LEFT,pg.K_RIGHT,pg.K_UP,pg.K_DOWN,pg.K_a,pg.K_d,pg.K_w,pg.K_s):
                        g.reset()
            elif e.type == pg.MOUSEBUTTONDOWN:
                swipe_start = e.pos
            elif e.type == pg.MOUSEBUTTONUP:
                if swipe_start:
                    d = direction_from_swipe(swipe_start, e.pos)
                    swipe_start = None
                    if d and not g.game_over:
                        g.move(d)
                    elif d and g.game_over:
                        g.reset()

        g.update(dt)
        g.draw()
        pg.display.flip()

if __name__ == "__main__":
    main()
