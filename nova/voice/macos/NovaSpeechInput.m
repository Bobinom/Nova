#include <dispatch/dispatch.h>
#include <objc/message.h>
#include <objc/runtime.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef long NSInteger;
typedef unsigned long NSUInteger;

static const char *ErrorPath = NULL;

static SEL Selector(const char *name) {
    return sel_registerName(name);
}

static id String(const char *value) {
    Class cls = objc_getClass("NSString");
    return ((id (*)(id, SEL, const char *))objc_msgSend)(
        (id)cls, Selector("stringWithUTF8String:"), value
    );
}

static const char *UTF8(id value) {
    if (value == nil) {
        return "";
    }
    return ((const char *(*)(id, SEL))objc_msgSend)(
        value, Selector("UTF8String")
    );
}

static void Fail(const char *message) {
    if (ErrorPath != NULL) {
        FILE *handle = fopen(ErrorPath, "w");
        if (handle != NULL) {
            fprintf(handle, "%s\n", message);
            fclose(handle);
        }
    }
    fprintf(stderr, "%s\n", message);
    exit(1);
}

static void RunLoopFor(double seconds) {
    Class runLoopClass = objc_getClass("NSRunLoop");
    id runLoop = ((id (*)(id, SEL))objc_msgSend)(
        (id)runLoopClass, Selector("currentRunLoop")
    );
    Class dateClass = objc_getClass("NSDate");
    id deadline = ((id (*)(id, SEL, double))objc_msgSend)(
        (id)dateClass,
        Selector("dateWithTimeIntervalSinceNow:"),
        seconds
    );
    ((void (*)(id, SEL, id))objc_msgSend)(
        runLoop, Selector("runUntilDate:"), deadline
    );
}

static const char *ArgumentAfter(
    int argc,
    const char *argv[],
    const char *name
) {
    for (int index = 1; index + 1 < argc; index++) {
        if (strcmp(argv[index], name) == 0) {
            return argv[index + 1];
        }
    }
    return NULL;
}

static void RequestPermissions(void) {
    Class speech = objc_getClass("SFSpeechRecognizer");
    NSInteger speechStatus = ((NSInteger (*)(id, SEL))objc_msgSend)(
        (id)speech, Selector("authorizationStatus")
    );
    if (speechStatus == 0) {
        dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
        void (^authorization)(NSInteger) = ^(NSInteger status) {
            (void)status;
            dispatch_semaphore_signal(semaphore);
        };
        ((void (*)(id, SEL, id))objc_msgSend)(
            (id)speech,
            Selector("requestAuthorization:"),
            authorization
        );
        dispatch_semaphore_wait(
            semaphore,
            dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_SEC)
        );
        speechStatus = ((NSInteger (*)(id, SEL))objc_msgSend)(
            (id)speech, Selector("authorizationStatus")
        );
    }
    if (speechStatus != 3) {
        Fail("Speech Recognition permission was denied. Enable Nova Speech Input in System Settings > Privacy & Security > Speech Recognition.");
    }

    Class capture = objc_getClass("AVCaptureDevice");
    id audioType = String("soun");
    NSInteger microphoneStatus =
        ((NSInteger (*)(id, SEL, id))objc_msgSend)(
            (id)capture,
            Selector("authorizationStatusForMediaType:"),
            audioType
        );
    if (microphoneStatus == 0) {
        dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
        void (^authorization)(BOOL) = ^(BOOL granted) {
            (void)granted;
            dispatch_semaphore_signal(semaphore);
        };
        ((void (*)(id, SEL, id, id))objc_msgSend)(
            (id)capture,
            Selector("requestAccessForMediaType:completionHandler:"),
            audioType,
            authorization
        );
        dispatch_semaphore_wait(
            semaphore,
            dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_SEC)
        );
        microphoneStatus = ((NSInteger (*)(id, SEL, id))objc_msgSend)(
            (id)capture,
            Selector("authorizationStatusForMediaType:"),
            audioType
        );
    }
    if (microphoneStatus != 3) {
        Fail("Microphone permission was denied. Enable Nova Speech Input in System Settings > Privacy & Security > Microphone.");
    }
}

int main(int argc, const char *argv[]) {
    ErrorPath = ArgumentAfter(argc, argv, "--error");
    Class poolClass = objc_getClass("NSAutoreleasePool");
    id pool = ((id (*)(id, SEL))objc_msgSend)(
        (id)poolClass, Selector("alloc")
    );
    pool = ((id (*)(id, SEL))objc_msgSend)(pool, Selector("init"));

    const char *localeName = ArgumentAfter(argc, argv, "--locale");
    if (localeName == NULL) {
        localeName = "en-US";
    }
    const char *secondsValue = ArgumentAfter(argc, argv, "--seconds");
    double seconds = secondsValue == NULL ? 7 : atof(secondsValue);
    if (seconds < 2) seconds = 2;
    if (seconds > 20) seconds = 20;

    Class localeClass = objc_getClass("NSLocale");
    id locale = ((id (*)(id, SEL, id))objc_msgSend)(
        (id)localeClass,
        Selector("localeWithLocaleIdentifier:"),
        String(localeName)
    );
    Class recognizerClass = objc_getClass("SFSpeechRecognizer");
    id recognizer = ((id (*)(id, SEL))objc_msgSend)(
        (id)recognizerClass, Selector("alloc")
    );
    recognizer = ((id (*)(id, SEL, id))objc_msgSend)(
        recognizer,
        Selector("initWithLocale:"),
        locale
    );
    if (recognizer == nil) {
        Fail("Speech recognition is unavailable for the configured locale.");
    }
    BOOL recognizerAvailable = ((BOOL (*)(id, SEL))objc_msgSend)(
        recognizer, Selector("isAvailable")
    );
    if (!recognizerAvailable) {
        Fail("Apple's speech recognizer is temporarily unavailable.");
    }
    BOOL onDevice = ((BOOL (*)(id, SEL))objc_msgSend)(
        recognizer, Selector("supportsOnDeviceRecognition")
    );
    if (!onDevice) {
        Fail("On-device speech recognition is unavailable for the configured locale.");
    }
    if (ArgumentAfter(argc, argv, "--check") != NULL ||
        (argc > 1 && strcmp(argv[1], "--check") == 0)) {
        printf("ready\n");
        ((void (*)(id, SEL))objc_msgSend)(pool, Selector("drain"));
        return 0;
    }

    RequestPermissions();

    Class engineClass = objc_getClass("AVAudioEngine");
    id engine = ((id (*)(id, SEL))objc_msgSend)(
        (id)engineClass, Selector("alloc")
    );
    engine = ((id (*)(id, SEL))objc_msgSend)(engine, Selector("init"));
    id input = ((id (*)(id, SEL))objc_msgSend)(
        engine, Selector("inputNode")
    );
    id format = ((id (*)(id, SEL, NSUInteger))objc_msgSend)(
        input, Selector("outputFormatForBus:"), 0
    );
    double sampleRate = ((double (*)(id, SEL))objc_msgSend)(
        format, Selector("sampleRate")
    );
    NSUInteger channelCount = ((NSUInteger (*)(id, SEL))objc_msgSend)(
        format, Selector("channelCount")
    );
    if (sampleRate <= 0 || channelCount == 0) {
        Fail("The microphone returned an invalid audio format.");
    }

    Class requestClass = objc_getClass(
        "SFSpeechAudioBufferRecognitionRequest"
    );
    id request = ((id (*)(id, SEL))objc_msgSend)(
        (id)requestClass, Selector("alloc")
    );
    request = ((id (*)(id, SEL))objc_msgSend)(request, Selector("init"));
    ((void (*)(id, SEL, BOOL))objc_msgSend)(
        request, Selector("setShouldReportPartialResults:"), YES
    );
    ((void (*)(id, SEL, BOOL))objc_msgSend)(
        request, Selector("setRequiresOnDeviceRecognition:"), YES
    );

    __block NSUInteger audioBufferCount = 0;
    void (^audioTap)(id, id) = ^(id buffer, id when) {
        (void)when;
        audioBufferCount += 1;
        ((void (*)(id, SEL, id))objc_msgSend)(
            request, Selector("appendAudioPCMBuffer:"), buffer
        );
    };
    ((void (*)(id, SEL, NSUInteger, unsigned int, id, id))objc_msgSend)(
        input,
        Selector("installTapOnBus:bufferSize:format:block:"),
        0,
        1024,
        format,
        audioTap
    );

    __block id transcript = nil;
    __block id recognitionError = nil;
    __block BOOL recognitionFinished = NO;
    void (^resultHandler)(id, id) = ^(id result, id error) {
        if (result != nil) {
            id best = ((id (*)(id, SEL))objc_msgSend)(
                result, Selector("bestTranscription")
            );
            id formatted = ((id (*)(id, SEL))objc_msgSend)(
                best, Selector("formattedString")
            );
            transcript = ((id (*)(id, SEL))objc_msgSend)(
                formatted, Selector("copy")
            );
            BOOL final = ((BOOL (*)(id, SEL))objc_msgSend)(
                result, Selector("isFinal")
            );
            if (final) recognitionFinished = YES;
        }
        if (error != nil) {
            recognitionError = ((id (*)(id, SEL))objc_msgSend)(
                error, Selector("retain")
            );
            recognitionFinished = YES;
        }
    };
    id task = ((id (*)(id, SEL, id, id))objc_msgSend)(
        recognizer,
        Selector("recognitionTaskWithRequest:resultHandler:"),
        request,
        resultHandler
    );

    ((void (*)(id, SEL))objc_msgSend)(engine, Selector("prepare"));
    id startError = nil;
    BOOL started = ((BOOL (*)(id, SEL, id *))objc_msgSend)(
        engine, Selector("startAndReturnError:"), &startError
    );
    if (!started) {
        id description = ((id (*)(id, SEL))objc_msgSend)(
            startError, Selector("localizedDescription")
        );
        char message[1024];
        snprintf(
            message,
            sizeof(message),
            "Could not start the microphone: %s",
            UTF8(description)
        );
        Fail(message);
    }

    RunLoopFor(seconds);
    ((void (*)(id, SEL))objc_msgSend)(engine, Selector("stop"));
    ((void (*)(id, SEL, NSUInteger))objc_msgSend)(
        input, Selector("removeTapOnBus:"), 0
    );
    ((void (*)(id, SEL))objc_msgSend)(request, Selector("endAudio"));
    for (int attempt = 0; attempt < 100 && !recognitionFinished; attempt++) {
        RunLoopFor(0.1);
    }
    ((void (*)(id, SEL))objc_msgSend)(task, Selector("cancel"));

    const char *text = UTF8(transcript);
    if (text[0] == '\0') {
        if (recognitionError != nil) {
            id description = ((id (*)(id, SEL))objc_msgSend)(
                recognitionError, Selector("localizedDescription")
            );
            const char *details = UTF8(description);
            if (strstr(details, "No speech detected") != NULL) {
                Fail("No speech was detected. In System Settings > Sound > Input, select the microphone you are speaking into and verify that its input-level meter moves.");
            }
            char message[1024];
            snprintf(
                message,
                sizeof(message),
                "Speech recognition failed: %s",
                details
            );
            Fail(message);
        } else if (audioBufferCount == 0) {
            Fail("The microphone did not deliver any audio. Check the selected input device and Microphone permission.");
        } else {
            Fail("The microphone captured audio, but no speech was recognized.");
        }
    }
    const char *outputPath = ArgumentAfter(argc, argv, "--output");
    if (outputPath != NULL) {
        FILE *handle = fopen(outputPath, "w");
        if (handle == NULL) {
            Fail("Could not write the recognized transcript.");
        }
        fprintf(handle, "%s\n", text);
        fclose(handle);
    } else {
        printf("%s\n", text);
    }
    ((void (*)(id, SEL))objc_msgSend)(pool, Selector("drain"));
    return 0;
}
