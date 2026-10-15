#include <SDL.h>
#include <GLES2/gl2.h>
#include <stdint.h>
#include <stdio.h>

#include "../source/rgb24_frame.h"
#include "../source/switch_presenter_layout.h"
#include "../source/switch_rgb24_presenter.h"

#define WINDOW_WIDTH 1280
#define WINDOW_HEIGHT 720
#define FRAME_WIDTH 321
#define FRAME_HEIGHT 240
#define FRAME_STRIDE (FRAME_WIDTH * 3)

static uint8_t frame_pixels[FRAME_STRIDE * FRAME_HEIGHT];

static void fill_bottom_up_rgb24(void) {
    for (int y = 0; y < FRAME_HEIGHT; ++y) {
        for (int x = 0; x < FRAME_WIDTH; ++x) {
            uint8_t *p = frame_pixels + (size_t)y * FRAME_STRIDE + (size_t)x * 3u;
            int top_y = FRAME_HEIGHT - 1 - y;
            if (x < 24 && top_y < 24) {
                p[0] = 255; p[1] = 0; p[2] = 0;
            } else if (x >= FRAME_WIDTH - 24 && top_y < 24) {
                p[0] = 0; p[1] = 255; p[2] = 0;
            } else if (x < 24 && top_y >= FRAME_HEIGHT - 24) {
                p[0] = 0; p[1] = 0; p[2] = 255;
            } else if (x >= FRAME_WIDTH - 24 && top_y >= FRAME_HEIGHT - 24) {
                p[0] = 255; p[1] = 255; p[2] = 0;
            } else {
                p[0] = (uint8_t)((x * 255) / (FRAME_WIDTH - 1));
                p[1] = (uint8_t)((top_y * 255) / (FRAME_HEIGHT - 1));
                p[2] = 48;
            }
        }
    }
}

static void update_animation_marker(unsigned frame_number) {
    const uint8_t red = (uint8_t)(frame_number & 0xffu);
    const uint8_t green = (uint8_t)(255u - red);
    const uint8_t blue = (uint8_t)((frame_number * 37u) & 0xffu);
    for (int y = 96; y < 128; ++y) {
        const int storage_y = FRAME_HEIGHT - 1 - y;
        for (int x = 144; x < 176; ++x) {
            uint8_t *p = frame_pixels + (size_t)storage_y * FRAME_STRIDE + (size_t)x * 3u;
            p[0] = red;
            p[1] = green;
            p[2] = blue;
        }
    }
}

int main(void) {
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\\n", SDL_GetError());
        return 1;
    }
    if (SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES) != 0 ||
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2) != 0 ||
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0) != 0 ||
        SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1) != 0) {
        fprintf(stderr, "SDL_GL_SetAttribute failed: %s\\n", SDL_GetError());
        SDL_Quit();
        return 2;
    }
    SDL_Window *window = SDL_CreateWindow("Vandal Hearts RGB24 Presenter Probe",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, WINDOW_WIDTH, WINDOW_HEIGHT,
        SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\\n", SDL_GetError());
        SDL_Quit();
        return 3;
    }
    SDL_GLContext context = SDL_GL_CreateContext(window);
    if (!context) {
        fprintf(stderr, "SDL_GL_CreateContext failed: %s\\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 4;
    }
    SDL_GL_SetSwapInterval(1);
    glDisable(GL_DEPTH_TEST);

    VhSwitchRgb24Presenter presenter;
    if (!vh_switch_rgb24_presenter_init(&presenter)) {
        fprintf(stderr, "RGB24 presenter initialization failed\\n");
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }
    fill_bottom_up_rgb24();
    const VhRgb24Frame frame = {frame_pixels, FRAME_STRIDE, FRAME_WIDTH, FRAME_HEIGHT};
    VhPresenterRect destination;
    if (!vh_rgb24_frame_valid(&frame) ||
        !vh_presenter_fit_rect(frame.width, frame.height, WINDOW_WIDTH, WINDOW_HEIGHT, &destination)) {
        fprintf(stderr, "RGB24 frame/layout validation failed\\n");
        vh_switch_rgb24_presenter_destroy(&presenter);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 6;
    }
    fprintf(stderr, "Presenter viewport: x=%d y=%d width=%d height=%d\\n",
            destination.x, destination.y, destination.width, destination.height);
    if (!vh_switch_rgb24_presenter_upload(&presenter, &frame)) {
        vh_switch_rgb24_presenter_destroy(&presenter);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 7;
    }
    fprintf(stderr, "RGB24 upload: %dx%d stride=%d unpack_alignment=1 gl_error=0x0000\\n",
            FRAME_WIDTH, FRAME_HEIGHT, FRAME_STRIDE);

    /* A rejected frame must not invalidate the last successfully uploaded texture. */
    const VhRgb24Frame invalid_frame = {frame_pixels, 0u, FRAME_WIDTH, FRAME_HEIGHT};
    if (vh_switch_rgb24_presenter_upload(&presenter, &invalid_frame)) {
        fprintf(stderr, "RGB24 presenter accepted invalid frame metadata\\n");
        vh_switch_rgb24_presenter_destroy(&presenter);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 9;
    }
    static uint8_t resized_pixels[17 * 9 * 3];
    for (int y = 0; y < 9; ++y) {
        for (int x = 0; x < 17; ++x) {
            uint8_t *p = resized_pixels + ((size_t)y * 17u + (size_t)x) * 3u;
            p[0] = (uint8_t)(x * 15);
            p[1] = (uint8_t)(y * 28);
            p[2] = 96;
        }
    }
    const VhRgb24Frame resized_frame = {resized_pixels, 17u * 3u, 17, 9};
    if (!vh_switch_rgb24_presenter_upload(&presenter, &resized_frame) ||
        presenter.frame_width != 17 || presenter.frame_height != 9 ||
        !vh_switch_rgb24_presenter_upload(&presenter, &frame) ||
        presenter.frame_width != FRAME_WIDTH || presenter.frame_height != FRAME_HEIGHT) {
        fprintf(stderr, "RGB24 presenter resize round-trip failed\\n");
        vh_switch_rgb24_presenter_destroy(&presenter);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 12;
    }
    fprintf(stderr, "RGB24 resize round-trip: PASS\\n");

    if (!vh_switch_rgb24_presenter_draw(&presenter, WINDOW_WIDTH, WINDOW_HEIGHT)) {
        fprintf(stderr, "RGB24 presenter lost valid frame after rejected upload\\n");
        vh_switch_rgb24_presenter_destroy(&presenter);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 10;
    }
    fprintf(stderr, "RGB24 rejected-upload recovery: PASS\\n");

    int running = 1;
    int result = 0;
    unsigned frame_number = 0;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) if (event.type == SDL_QUIT) running = 0;

        /* Exercise the real per-frame path: mutate borrowed RGB24 pixels, upload, then draw. */
        update_animation_marker(frame_number++);
        if (!vh_switch_rgb24_presenter_upload(&presenter, &frame)) {
            fprintf(stderr, "RGB24 per-frame upload failed at frame %u\\n", frame_number);
            result = 11;
            break;
        }
        glViewport(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT);
        glClearColor(0.02f, 0.02f, 0.03f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        if (!vh_switch_rgb24_presenter_draw(&presenter, WINDOW_WIDTH, WINDOW_HEIGHT)) {
            result = 8;
            break;
        }
        SDL_GL_SwapWindow(window);
        SDL_Delay(16);
    }
    fprintf(stderr, "RGB24 repeated upload frames: %u\\n", frame_number);
    vh_switch_rgb24_presenter_destroy(&presenter);
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return result;
}
