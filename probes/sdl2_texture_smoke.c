#include <SDL.h>
#include <GLES2/gl2.h>
#include <stdio.h>

#include "game_state.h"

#define WINDOW_WIDTH 1280
#define WINDOW_HEIGHT 720
#define GRID_WIDTH 8
#define GRID_HEIGHT 6
#define CELL_SIZE 64
#define GRID_X 384
#define GRID_Y 120
#define MOVE_RANGE 2

static Uint8 frame_pixels[WINDOW_WIDTH * WINDOW_HEIGHT * 4];

static void fill_rect(int x, int y, int width, int height,
                      Uint8 r, Uint8 g, Uint8 b) {
    if (x < 0) { width += x; x = 0; }
    if (y < 0) { height += y; y = 0; }
    if (x + width > WINDOW_WIDTH) width = WINDOW_WIDTH - x;
    if (y + height > WINDOW_HEIGHT) height = WINDOW_HEIGHT - y;
    if (width <= 0 || height <= 0) return;

    for (int row = y; row < y + height; row++) {
        Uint8 *pixel = frame_pixels + ((size_t)row * WINDOW_WIDTH + (size_t)x) * 4;
        for (int col = 0; col < width; col++, pixel += 4) {
            pixel[0] = r;
            pixel[1] = g;
            pixel[2] = b;
            pixel[3] = 255;
        }
    }
}

static void draw_cpu_frame(const VhGameState *state) {
    fill_rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT, 12, 18, 34);
    for (int y = 0; y < GRID_HEIGHT; y++) {
        for (int x = 0; x < GRID_WIDTH; x++) {
            const int px = GRID_X + x * CELL_SIZE;
            const int py = GRID_Y + y * CELL_SIZE;
            if (state->hero_selected &&
                vh_manhattan_distance(state->hero_x, state->hero_y, x, y) <= MOVE_RANGE &&
                !(x == state->enemy_x && y == state->enemy_y)) {
                fill_rect(px + 2, py + 2, CELL_SIZE - 4, CELL_SIZE - 4, 43, 91, 91);
            } else if ((x + y) & 1) {
                fill_rect(px + 2, py + 2, CELL_SIZE - 4, CELL_SIZE - 4, 39, 54, 75);
            } else {
                fill_rect(px + 2, py + 2, CELL_SIZE - 4, CELL_SIZE - 4, 34, 48, 68);
            }

            fill_rect(px, py, CELL_SIZE, 2, 58, 74, 96);
            fill_rect(px, py + CELL_SIZE - 2, CELL_SIZE, 2, 58, 74, 96);
            fill_rect(px, py, 2, CELL_SIZE, 58, 74, 96);
            fill_rect(px + CELL_SIZE - 2, py, 2, CELL_SIZE, 58, 74, 96);

            if (x == state->hero_x && y == state->hero_y)
                fill_rect(px + 16, py + 16, 32, 32, 86, 190, 244);
            if (x == state->enemy_x && y == state->enemy_y)
                fill_rect(px + 16, py + 16, 32, 32, 235, 89, 98);
            if (x == state->cursor_x && y == state->cursor_y) {
                fill_rect(px + 4, py + 4, CELL_SIZE - 8, 4, 255, 219, 102);
                fill_rect(px + 4, py + CELL_SIZE - 8, CELL_SIZE - 8, 4, 255, 219, 102);
                fill_rect(px + 4, py + 4, 4, CELL_SIZE - 8, 255, 219, 102);
                fill_rect(px + CELL_SIZE - 8, py + 4, 4, CELL_SIZE - 8, 255, 219, 102);
            }
        }
    }
}

static GLuint compile_shader(GLenum type, const char *source) {
    GLuint shader = glCreateShader(type);
    GLint compiled = GL_FALSE;
    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
    if (compiled != GL_TRUE) {
        char log[512] = {0};
        glGetShaderInfoLog(shader, sizeof(log), NULL, log);
        fprintf(stderr, "Shader compile failed: %s\n", log);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

static GLuint create_program(void) {
    static const char *vertex_source =
        "attribute vec2 aPosition;\n"
        "attribute vec2 aTexCoord;\n"
        "varying vec2 vTexCoord;\n"
        "void main() { gl_Position = vec4(aPosition, 0.0, 1.0); vTexCoord = aTexCoord; }\n";
    static const char *fragment_source =
        "precision mediump float;\n"
        "uniform sampler2D uTexture;\n"
        "varying vec2 vTexCoord;\n"
        "void main() { gl_FragColor = texture2D(uTexture, vTexCoord); }\n";
    GLuint vertex = compile_shader(GL_VERTEX_SHADER, vertex_source);
    GLuint fragment = compile_shader(GL_FRAGMENT_SHADER, fragment_source);
    if (!vertex || !fragment) {
        if (vertex) glDeleteShader(vertex);
        if (fragment) glDeleteShader(fragment);
        return 0;
    }
    GLuint program = glCreateProgram();
    glAttachShader(program, vertex);
    glAttachShader(program, fragment);
    glBindAttribLocation(program, 0, "aPosition");
    glBindAttribLocation(program, 1, "aTexCoord");
    glLinkProgram(program);
    glDeleteShader(vertex);
    glDeleteShader(fragment);
    GLint linked = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (linked != GL_TRUE) {
        char log[512] = {0};
        glGetProgramInfoLog(program, sizeof(log), NULL, log);
        fprintf(stderr, "Shader link failed: %s\n", log);
        glDeleteProgram(program);
        return 0;
    }
    return program;
}

static void move_cursor(VhGameState *state, int dx, int dy) {
    vh_move_cursor(state, dx, dy, GRID_WIDTH, GRID_HEIGHT);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK) != 0) {
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
        "Vandal Hearts SDL2 Texture Upload Probe",
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

    GLuint program = create_program();
    if (!program) {
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }

    static const GLfloat quad[] = {
        -1.0f, -1.0f, 0.0f, 1.0f,
         1.0f, -1.0f, 1.0f, 1.0f,
        -1.0f,  1.0f, 0.0f, 0.0f,
         1.0f,  1.0f, 1.0f, 0.0f
    };
    GLuint vbo = 0, texture = 0;
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);

    VhGameState state = {1, 2, 1, 2, 6, 3, 0};
    draw_cpu_frame(&state);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, WINDOW_WIDTH, WINDOW_HEIGHT, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, frame_pixels);
    GLint sampler = glGetUniformLocation(program, "uTexture");

    const int joystick_count = SDL_NumJoysticks();
    fprintf(stderr, "SDL joystick count: %d\n", joystick_count);
    SDL_Joystick *joystick = joystick_count > 0 ? SDL_JoystickOpen(0) : NULL;
    if (!joystick) fprintf(stderr, "SDL_JoystickOpen(0) failed: %s\n", SDL_GetError());

    int running = 1;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = 0;
            if (event.type == SDL_KEYDOWN) {
                switch (event.key.keysym.sym) {
                    case SDLK_ESCAPE: running = 0; break;
                    case SDLK_LEFT: move_cursor(&state, -1, 0); break;
                    case SDLK_RIGHT: move_cursor(&state, 1, 0); break;
                    case SDLK_UP: move_cursor(&state, 0, -1); break;
                    case SDLK_DOWN: move_cursor(&state, 0, 1); break;
                    case SDLK_RETURN:
                    case SDLK_SPACE:
                        vh_activate_cursor(&state, GRID_WIDTH, GRID_HEIGHT, MOVE_RANGE);
                        break;
                    case SDLK_x: vh_cancel_selection(&state); break;
                    default: break;
                }
            }
            /* devkitPro's Switch SDL2 backend reports pad buttons as SDL_JOYBUTTONDOWN. */
            if (joystick && event.type == SDL_JOYBUTTONDOWN &&
                event.jbutton.which == SDL_JoystickInstanceID(joystick)) {
                switch (event.jbutton.button) {
                    case 12: move_cursor(&state, -1, 0); break; /* D-pad left */
                    case 14: move_cursor(&state, 1, 0); break;  /* D-pad right */
                    case 13: move_cursor(&state, 0, -1); break; /* D-pad up */
                    case 15: move_cursor(&state, 0, 1); break;  /* D-pad down */
                    case 0: vh_activate_cursor(&state, GRID_WIDTH, GRID_HEIGHT, MOVE_RANGE); break; /* A */
                    case 1: vh_cancel_selection(&state); break; /* B */
                    case 10: running = 0; break; /* Plus */
                    default: break;
                }
            }
        }

        draw_cpu_frame(&state);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, texture);
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT,
                        GL_RGBA, GL_UNSIGNED_BYTE, frame_pixels);
        glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        glUseProgram(program);
        glUniform1i(sampler, 0);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glEnableVertexAttribArray(0);
        glEnableVertexAttribArray(1);
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), (const void *)0);
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat),
                              (const void *)(2 * sizeof(GLfloat)));
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        SDL_GL_SwapWindow(window);
        SDL_Delay(16);
    }

    if (joystick) SDL_JoystickClose(joystick);
    glDeleteTextures(1, &texture);
    glDeleteBuffers(1, &vbo);
    glDeleteProgram(program);
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
