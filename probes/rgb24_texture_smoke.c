#include <SDL.h>
#include <GLES2/gl2.h>
#include <stdint.h>
#include <stdio.h>

#include "../source/rgb24_frame.h"
#include "../source/switch_presenter_layout.h"

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
            /* Source memory is bottom-up, like the audited PC-port scratch buffer. */
            int top_y = FRAME_HEIGHT - 1 - y;
            if (x < 24 && top_y < 24) {
                p[0] = 255; p[1] = 0; p[2] = 0;       /* top-left: red */
            } else if (x >= FRAME_WIDTH - 24 && top_y < 24) {
                p[0] = 0; p[1] = 255; p[2] = 0;       /* top-right: green */
            } else if (x < 24 && top_y >= FRAME_HEIGHT - 24) {
                p[0] = 0; p[1] = 0; p[2] = 255;       /* bottom-left: blue */
            } else if (x >= FRAME_WIDTH - 24 && top_y >= FRAME_HEIGHT - 24) {
                p[0] = 255; p[1] = 255; p[2] = 0;     /* bottom-right: yellow */
            } else {
                p[0] = (uint8_t)((x * 255) / (FRAME_WIDTH - 1));
                p[1] = (uint8_t)((top_y * 255) / (FRAME_HEIGHT - 1));
                p[2] = 48;
            }
        }
    }
}

static GLuint compile_shader(GLenum type, const char *source) {
    GLuint shader = glCreateShader(type);
    GLint ok = GL_FALSE;
    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok != GL_TRUE) {
        char log[512] = {0};
        glGetShaderInfoLog(shader, sizeof(log), NULL, log);
        fprintf(stderr, "RGB24 shader compile failed: %s\n", log);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

static GLuint create_program(void) {
    static const char *vs =
        "attribute vec2 aPosition; attribute vec2 aTexCoord; varying vec2 vTexCoord; "
        "void main(){ gl_Position=vec4(aPosition,0.0,1.0); vTexCoord=aTexCoord; }";
    static const char *fs =
        "precision mediump float; uniform sampler2D uTexture; varying vec2 vTexCoord; "
        "void main(){ gl_FragColor=texture2D(uTexture,vTexCoord); }";
    GLuint vertex = compile_shader(GL_VERTEX_SHADER, vs);
    GLuint fragment = compile_shader(GL_FRAGMENT_SHADER, fs);
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
        fprintf(stderr, "RGB24 shader link failed: %s\n", log);
        glDeleteProgram(program);
        return 0;
    }
    return program;
}

int main(void) {
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
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
    SDL_Window *window = SDL_CreateWindow("Vandal Hearts RGB24 Upload Probe",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, WINDOW_WIDTH, WINDOW_HEIGHT,
        SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
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
    /* Texture coordinates deliberately preserve the bottom-up source orientation. */
    static const GLfloat quad[] = {
        -1.0f, -1.0f, 0.0f, 0.0f,
         1.0f, -1.0f, 1.0f, 0.0f,
        -1.0f,  1.0f, 0.0f, 1.0f,
         1.0f,  1.0f, 1.0f, 1.0f
    };
    GLuint vbo = 0, texture = 0;
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    fill_bottom_up_rgb24();
    const VhRgb24Frame frame = {frame_pixels, FRAME_STRIDE, FRAME_WIDTH, FRAME_HEIGHT};
    VhPresenterRect destination;
    if (!vh_rgb24_frame_valid(&frame) ||
        !vh_presenter_fit_rect(frame.width, frame.height,
                               WINDOW_WIDTH, WINDOW_HEIGHT, &destination)) {
        fprintf(stderr, "RGB24 presenter rejected frame/layout\\n");
        glDeleteBuffers(1, &vbo);
        glDeleteProgram(program);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 6;
    }
    fprintf(stderr, "Presenter viewport: x=%d y=%d width=%d height=%d\\n",
            destination.x, destination.y, destination.width, destination.height);
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    /* 321 RGB pixels = 963 bytes/row, intentionally not divisible by four. */
    /* Drain earlier errors so this checkpoint reports the upload itself. */
    while (glGetError() != GL_NO_ERROR) {}
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, frame.width, frame.height, 0,
                 GL_RGB, GL_UNSIGNED_BYTE, frame.pixels);
    GLenum upload_error = glGetError();
    fprintf(stderr, "RGB24 upload: %dx%d stride=%d unpack_alignment=1 gl_error=0x%04x\n",
            FRAME_WIDTH, FRAME_HEIGHT, FRAME_STRIDE, (unsigned int)upload_error);
    if (upload_error != GL_NO_ERROR) {
        fprintf(stderr, "RGB24 texture upload failed; refusing to present an invalid texture\\n");
        glDeleteTextures(1, &texture);
        glDeleteBuffers(1, &vbo);
        glDeleteProgram(program);
        SDL_GL_DeleteContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 7;
    }
    GLint sampler = glGetUniformLocation(program, "uTexture");

    int running = 1;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) if (event.type == SDL_QUIT) running = 0;
        glClearColor(0.02f, 0.02f, 0.03f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        /* Fit RGB24 frame into the window without cropping or stretching. */
        glViewport(destination.x, WINDOW_HEIGHT - destination.y - destination.height,
                   destination.width, destination.height);
        glUseProgram(program);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, texture);
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
    glDeleteTextures(1, &texture);
    glDeleteBuffers(1, &vbo);
    glDeleteProgram(program);
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
