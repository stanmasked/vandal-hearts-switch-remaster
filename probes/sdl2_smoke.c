#include <SDL.h>
#include <stdio.h>

#include "game_rules.h"

#define WINDOW_WIDTH 1280
#define WINDOW_HEIGHT 720
#define GRID_WIDTH 8
#define GRID_HEIGHT 6
#define CELL_SIZE 64
#define GRID_X 384
#define GRID_Y 120
#define MOVE_RANGE 2

static void move_cursor(int *x, int *y, int dx, int dy) {
    *x += dx;
    *y += dy;
    if (*x < 0) *x = 0;
    if (*x >= GRID_WIDTH) *x = GRID_WIDTH - 1;
    if (*y < 0) *y = 0;
    if (*y >= GRID_HEIGHT) *y = GRID_HEIGHT - 1;
}

static void activate(int *cursor_x, int *cursor_y, int *hero_x, int *hero_y,
                     int enemy_x, int enemy_y, int *selected) {
    if (!*selected) {
        if (*cursor_x == *hero_x && *cursor_y == *hero_y) *selected = 1;
        return;
    }

    if (vh_can_move(*hero_x, *hero_y, *cursor_x, *cursor_y,
                    GRID_WIDTH, GRID_HEIGHT, MOVE_RANGE, enemy_x, enemy_y)) {
        *hero_x = *cursor_x;
        *hero_y = *cursor_y;
        *selected = 0;
    }
}

static void set_color(SDL_Renderer *renderer, Uint8 r, Uint8 g, Uint8 b) {
    SDL_SetRenderDrawColor(renderer, r, g, b, 255);
}

static void draw_frame(SDL_Renderer *renderer, int cursor_x, int cursor_y,
                       int hero_x, int hero_y, int enemy_x, int enemy_y,
                       int selected) {
    set_color(renderer, 12, 18, 34);
    SDL_RenderClear(renderer);

    for (int y = 0; y < GRID_HEIGHT; y++) {
        for (int x = 0; x < GRID_WIDTH; x++) {
            SDL_Rect tile = {
                GRID_X + x * CELL_SIZE + 2,
                GRID_Y + y * CELL_SIZE + 2,
                CELL_SIZE - 4,
                CELL_SIZE - 4
            };
            if (selected &&
                vh_manhattan_distance(hero_x, hero_y, x, y) <= MOVE_RANGE &&
                !(x == enemy_x && y == enemy_y)) {
                set_color(renderer, 43, 91, 91);
            } else if ((x + y) & 1) {
                set_color(renderer, 39, 54, 75);
            } else {
                set_color(renderer, 34, 48, 68);
            }
            SDL_RenderFillRect(renderer, &tile);

            SDL_Rect border = {
                GRID_X + x * CELL_SIZE,
                GRID_Y + y * CELL_SIZE,
                CELL_SIZE,
                CELL_SIZE
            };
            set_color(renderer, 58, 74, 96);
            SDL_RenderDrawRect(renderer, &border);

            if (x == hero_x && y == hero_y) {
                SDL_Rect hero = {border.x + 16, border.y + 16, 32, 32};
                set_color(renderer, 86, 190, 244);
                SDL_RenderFillRect(renderer, &hero);
            }
            if (x == enemy_x && y == enemy_y) {
                SDL_Rect enemy = {border.x + 16, border.y + 16, 32, 32};
                set_color(renderer, 235, 89, 98);
                SDL_RenderFillRect(renderer, &enemy);
            }
            if (x == cursor_x && y == cursor_y) {
                SDL_Rect cursor = {border.x + 4, border.y + 4,
                                   CELL_SIZE - 8, CELL_SIZE - 8};
                set_color(renderer, 255, 219, 102);
                SDL_RenderDrawRect(renderer, &cursor);
            }
        }
    }

    SDL_Rect status = {WINDOW_WIDTH - 92, 48, 36, 36};
    if (selected) set_color(renderer, 255, 219, 102);
    else set_color(renderer, 86, 190, 244);
    SDL_RenderFillRect(renderer, &status);
    SDL_RenderPresent(renderer);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window *window = SDL_CreateWindow(
        "Vandal Hearts SDL2 Switch Probe",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        WINDOW_WIDTH, WINDOW_HEIGHT, SDL_WINDOW_SHOWN);
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 2;
    }

    SDL_Renderer *renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer) {
        fprintf(stderr, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 3;
    }

    SDL_GameController *controller = NULL;
    for (int i = 0; i < SDL_NumJoysticks(); i++) {
        if (SDL_IsGameController(i)) {
            controller = SDL_GameControllerOpen(i);
            if (controller) break;
        }
    }

    int cursor_x = 1, cursor_y = 2;
    int hero_x = 1, hero_y = 2;
    const int enemy_x = 6, enemy_y = 3;
    int selected = 0;
    int running = 1;

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = 0;
            if (event.type == SDL_KEYDOWN) {
                switch (event.key.keysym.sym) {
                    case SDLK_ESCAPE: running = 0; break;
                    case SDLK_LEFT: move_cursor(&cursor_x, &cursor_y, -1, 0); break;
                    case SDLK_RIGHT: move_cursor(&cursor_x, &cursor_y, 1, 0); break;
                    case SDLK_UP: move_cursor(&cursor_x, &cursor_y, 0, -1); break;
                    case SDLK_DOWN: move_cursor(&cursor_x, &cursor_y, 0, 1); break;
                    case SDLK_RETURN:
                    case SDLK_SPACE:
                        activate(&cursor_x, &cursor_y, &hero_x, &hero_y,
                                 enemy_x, enemy_y, &selected);
                        break;
                    case SDLK_x: selected = 0; break;
                    default: break;
                }
            }
            if (event.type == SDL_CONTROLLERBUTTONDOWN) {
                switch (event.cbutton.button) {
                    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: move_cursor(&cursor_x, &cursor_y, -1, 0); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: move_cursor(&cursor_x, &cursor_y, 1, 0); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_UP: move_cursor(&cursor_x, &cursor_y, 0, -1); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: move_cursor(&cursor_x, &cursor_y, 0, 1); break;
                    case SDL_CONTROLLER_BUTTON_A:
                        activate(&cursor_x, &cursor_y, &hero_x, &hero_y,
                                 enemy_x, enemy_y, &selected);
                        break;
                    case SDL_CONTROLLER_BUTTON_B: selected = 0; break;
                    case SDL_CONTROLLER_BUTTON_START: running = 0; break;
                    default: break;
                }
            }
        }

        draw_frame(renderer, cursor_x, cursor_y, hero_x, hero_y,
                   enemy_x, enemy_y, selected);
        SDL_Delay(16);
    }

    if (controller) SDL_GameControllerClose(controller);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
