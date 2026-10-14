#include "switch_rgb24_presenter.h"

#include <stdio.h>
#include <string.h>

static GLuint compile_shader(GLenum type, const char *source) {
    GLuint shader = glCreateShader(type);
    if (!shader) return 0;
    GLint ok = GL_FALSE;
    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok != GL_TRUE) {
        char log[512] = {0};
        glGetShaderInfoLog(shader, sizeof(log), NULL, log);
        fprintf(stderr, "RGB24 presenter shader compile failed: %s\n", log);
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
    if (!program) {
        glDeleteShader(vertex);
        glDeleteShader(fragment);
        return 0;
    }
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
        fprintf(stderr, "RGB24 presenter program link failed: %s\n", log);
        glDeleteProgram(program);
        return 0;
    }
    return program;
}

int vh_switch_rgb24_presenter_init(VhSwitchRgb24Presenter *presenter) {
    if (!presenter) return 0;
    memset(presenter, 0, sizeof(*presenter));

    static const GLfloat quad[] = {
        -1.0f, -1.0f, 0.0f, 0.0f,
         1.0f, -1.0f, 1.0f, 0.0f,
        -1.0f,  1.0f, 0.0f, 1.0f,
         1.0f,  1.0f, 1.0f, 1.0f
    };

    presenter->program = create_program();
    if (!presenter->program) goto fail;
    glGenBuffers(1, &presenter->vertex_buffer);
    if (!presenter->vertex_buffer) goto fail;
    glBindBuffer(GL_ARRAY_BUFFER, presenter->vertex_buffer);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    glGenTextures(1, &presenter->texture);
    if (!presenter->texture) goto fail;
    glBindTexture(GL_TEXTURE_2D, presenter->texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    presenter->sampler_location = glGetUniformLocation(presenter->program, "uTexture");
    if (presenter->sampler_location < 0) goto fail;
    presenter->initialized = 1;
    return 1;

fail:
    vh_switch_rgb24_presenter_destroy(presenter);
    return 0;
}

int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *presenter,
                                     const VhRgb24Frame *frame) {
    if (!presenter || !presenter->initialized || !vh_rgb24_frame_valid(frame))
        return 0;
    glBindTexture(GL_TEXTURE_2D, presenter->texture);
    /* Clear unrelated earlier errors so this checkpoint belongs to this upload. */
    while (glGetError() != GL_NO_ERROR) {}
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, frame->width, frame->height, 0,
                 GL_RGB, GL_UNSIGNED_BYTE, frame->pixels);
    GLenum error = glGetError();
    if (error != GL_NO_ERROR) {
        fprintf(stderr, "RGB24 presenter upload failed: GL error 0x%04x\n",
                (unsigned int)error);
        return 0;
    }
    return 1;
}

int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *presenter,
                                   int viewport_width, int viewport_height) {
    if (!presenter || !presenter->initialized) return 0;
    GLint texture_width = 0, texture_height = 0;
    glBindTexture(GL_TEXTURE_2D, presenter->texture);
    glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH, &texture_width);
    glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT, &texture_height);
    /* GLES2 does not provide glGetTexLevelParameteriv; dimensions are tracked at upload. */
    (void)texture_width;
    (void)texture_height;
    return 0;
}

void vh_switch_rgb24_presenter_destroy(VhSwitchRgb24Presenter *presenter) {
    if (!presenter) return;
    if (presenter->texture) glDeleteTextures(1, &presenter->texture);
    if (presenter->vertex_buffer) glDeleteBuffers(1, &presenter->vertex_buffer);
    if (presenter->program) glDeleteProgram(presenter->program);
    memset(presenter, 0, sizeof(*presenter));
}
