#include <SDL.h>
#include <GLES2/gl2.h>
#include <stdio.h>

#define WINDOW_WIDTH 1280
#define WINDOW_HEIGHT 720
#define GRID_WIDTH 8
#define GRID_HEIGHT 6
#define CELL_SIZE 64
#define GRID_X 384
#define GRID_Y 120

static void draw_rect(int x, int y, int width, int height,
                      GLfloat r, GLfloat g, GLfloat b) {
    glScissor(x, WINDOW_HEIGHT - y - height, width, height);
    glClearColor(r, g, b, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
}

static void draw_frame(void) {
    glEnable(GL_SCISSOR_TEST);
    draw_rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT, 0.047f, 0.071f, 0.133f);

    for (int y = 0; y < GRID_HEIGHT; y++) {
        for (int x = 0; x < GRID_WIDTH; x++) {
            const int px = GRID_X + x * CELL_SIZE;
            const int py = GRID_Y + y * CELL_SIZE;
            if ((x + y) & 1) {
                draw_rect(px + 2, py + 2, CELL_SIZE - 4, CELL_SIZE - 4,
                          0.153f, 0.212f, 0.294f);
            } else {
                draw_rect(px + 2, py + 2, CELL_SIZE - 4, CELL_SIZE - 4,
                          0.133f, 0.188f, 0.267f);
            }
            draw_rect(px, py, CELL_SIZE, 2, 0.227f, 0.290f, 0.376f);
            draw_rect(px, py + CELL_SIZE - 2, CELL_SIZE, 2, 0.227f, 0.290f, 0.376f);
            draw_rect(px, py, 2, CELL_SIZE, 0.227f, 0.290f, 0.376f);
            draw_rect(px + CELL_SIZE - 2, py, 2, CELL_SIZE, 0.227f, 0.290f, 0.376f);
        }
    }

    draw_rect(GRID_X + CELL_SIZE + 16, GRID_Y + 2 * CELL_SIZE + 16,
              32, 32, 0.337f, 0.745f, 0.957f);
    draw_rect(GRID_X + 6 * CELL_SIZE + 16, GRID_Y + 3 * CELL_SIZE + 16,
              32, 32, 0.922f, 0.349f, 0.384f);
    draw_rect(WINDOW_WIDTH - 92, 48, 36, 36, 0.337f, 0.745f, 0.957f);
    glDisable(GL_SCISSOR_TEST);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    if (SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES) != 0 ||
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2) != 0 ||
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0) != 0 ||
        SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1) != 0) {
        fprintf(stderr, "SDL_GL_SetAttribute failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 2;
    }

    SDL_Window *window = SDL_CreateWindow(
        "Vandal Hearts SDL2 OpenGL ES Probe",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        WINDOW_WIDTH, WINDOW_HEIGHT, SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 3;
    }

    SDL_GLContext context = SDL_GL_CreateContext(window);
    if (!context) {
        fprintf(stderr, "SDL_GL_CreateContext failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 4;
    }

    SDL_GL_SetSwapInterval(1);
    glViewport(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT);
    glDisable(GL_DEPTH_TEST);

    SDL_GameController *controller = NULL;
    for (int i = 0; i < SDL_NumJoysticks(); i++) {
        if (SDL_IsGameController(i)) {
            controller = SDL_GameControllerOpen(i);
            if (controller) break;
        }
    }

    int running = 1;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = 0;
            if (event.type == SDL_KEYDOWN && event.key.keysym.sym == SDLK_ESCAPE) {
                running = 0;
            }
            if (event.type == SDL_CONTROLLERBUTTONDOWN &&
                event.cbutton.button == SDL_CONTROLLER_BUTTON_START) {
                running = 0;
            }
        }
        draw_frame();
        SDL_GL_SwapWindow(window);
        SDL_Delay(16);
    }

    if (controller) SDL_GameControllerClose(controller);
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
