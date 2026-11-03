/* Real Ubuntu 7.3.0-10.10 EFI signature-list parser exercised in userspace.
 * All inputs are synthetic; no firmware variables or certificates are used.
 * This is a parser regression harness, NOT proof of kernel trust safety.
 */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define __init
#define pr_devel(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_info(...) ((void)0)

typedef struct { uint8_t bytes[16]; } efi_guid_t;
typedef struct {
    efi_guid_t signature_owner;
    uint8_t signature_data[];
} efi_signature_data_t;
typedef struct {
    efi_guid_t signature_type;
    uint32_t signature_list_size;
    uint32_t signature_header_size;
    uint32_t signature_size;
    uint8_t signature_header[];
} efi_signature_list_t;
typedef void (*efi_element_handler_t)(const char *, const void *, size_t);

static unsigned int handler_calls;
static size_t last_element_bytes;
static void handle_signature(const char *source, const void *data, size_t len)
{
    (void)source;
    if (!data) abort();
    handler_calls++;
    last_element_bytes = len;
}
static efi_element_handler_t handler_for_guid(const efi_guid_t *type)
{
    if (type->bytes[0] == 0x42)
        return handle_signature;
    return NULL;
}

/* Include the actual GPL-2.0+ Ubuntu kernel C parser, not a rewrite. */
#include "security/integrity/platform_certs/efi_parser.c"

#define CHECK(x) do { if (!(x)) {                                             \
    fprintf(stderr, "%s:%d failed: %s\n", __func__, __LINE__, #x);           \
    return 1;                                                                 \
} } while (0)

static void make_valid_list(uint8_t *b, size_t total_size)
{
    efi_signature_list_t *h = (void *)b;
    efi_signature_data_t *sig;
    memset(b, 0, total_size);
    h->signature_type.bytes[0] = 0x42;
    h->signature_list_size = (uint32_t)total_size;
    h->signature_header_size = 0;
    h->signature_size = (uint32_t)(total_size - sizeof(*h));
    sig = (void *)(b + sizeof(*h));
    sig->signature_data[0] = 0x92;
}

static int valid_single_and_double(void)
{
    uint8_t buf[2 * 76];
    make_valid_list(buf, 76);
    handler_calls = 0;
    CHECK(parse_efi_signature_list("synthetic:MokListXRT", buf, 76,
                                    handler_for_guid) == 0);
    CHECK(handler_calls == 1 && last_element_bytes == 32);
    make_valid_list(buf + 76, 76);
    handler_calls = 0;
    CHECK(parse_efi_signature_list("synthetic:MokListXRT", buf, sizeof(buf),
                                    handler_for_guid) == 0);
    CHECK(handler_calls == 2);
    return 0;
}
static int unknown_guid_ignored(void)
{
    uint8_t buf[76];
    make_valid_list(buf, sizeof(buf));
    buf[0] = 0x13;
    handler_calls = 0;
    CHECK(parse_efi_signature_list("synthetic:MokListRT", buf, sizeof(buf),
                                    handler_for_guid) == 0);
    CHECK(handler_calls == 0);
    return 0;
}
static int truncations_rejected(void)
{
    uint8_t buf[76];
    size_t n;
    make_valid_list(buf, sizeof(buf));
    /* An empty signature-list blob is valid (no entries). */
    CHECK(parse_efi_signature_list("empty", buf, 0,
                                    handler_for_guid) == 0);
    for (n = 1; n < sizeof(efi_signature_list_t); n++)
        CHECK(parse_efi_signature_list("truncated", buf, n,
                                        handler_for_guid) == -EBADMSG);
    /* Header valid but advertised length exceeds available bytes. */
    CHECK(parse_efi_signature_list("truncated", buf, sizeof(buf) - 1,
                                    handler_for_guid) == -EBADMSG);
    return 0;
}
static int invalid_lengths_rejected(void)
{
    uint8_t buf[76];
    efi_signature_list_t *h = (void *)buf;
    make_valid_list(buf, sizeof(buf));
    h->signature_list_size = 27;
    CHECK(parse_efi_signature_list("malformed", buf, sizeof(buf),
                                    handler_for_guid) == -EBADMSG);
    make_valid_list(buf, sizeof(buf));
    h->signature_header_size = 50;
    CHECK(parse_efi_signature_list("malformed", buf, sizeof(buf),
                                    handler_for_guid) == -EBADMSG);
    make_valid_list(buf, sizeof(buf));
    h->signature_size = 0;
    CHECK(parse_efi_signature_list("malformed", buf, sizeof(buf),
                                    handler_for_guid) == -EBADMSG);
    make_valid_list(buf, sizeof(buf));
    h->signature_size = 49;
    CHECK(parse_efi_signature_list("malformed", buf, sizeof(buf),
                                    handler_for_guid) == -EBADMSG);
    make_valid_list(buf, sizeof(buf));
    h->signature_list_size = 0xffffffffu;
    CHECK(parse_efi_signature_list("malformed", buf, sizeof(buf),
                                    handler_for_guid) == -EBADMSG);
    return 0;
}
static uint32_t rng = 0x5e6a3b19u;
static uint32_t next_rand(void)
{
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
}
static int deterministic_mutation_sweep(void)
{
    uint8_t buf[160];
    size_t iter, idx;
    int rc;
    for (iter = 0; iter < 1500; iter++) {
        make_valid_list(buf, 76);
        for (idx = 0; idx < 1 + iter % 5; idx++) {
            size_t offset = next_rand() % 76;
            buf[offset] ^= (uint8_t)(next_rand() & 0xffu);
        }
        handler_calls = 0;
        rc = parse_efi_signature_list("fuzzed", buf, 76, handler_for_guid);
        CHECK(rc == 0 || rc == -EBADMSG);
        /* Parser must never process more than the bounded 76-byte list. */
        CHECK(handler_calls <= 3);
    }
    return 0;
}

int main(void)
{
    struct {
        const char *name;
        int (*fn)(void);
    } tests[] = {
        {"single_and_double", valid_single_and_double},
        {"unknown_guid", unknown_guid_ignored},
        {"truncations", truncations_rejected},
        {"malformed_lengths", invalid_lengths_rejected},
        {"deterministic_mutations", deterministic_mutation_sweep},
    };
    size_t i;
    for (i = 0; i < sizeof(tests)/sizeof(tests[0]); i++) {
        if (tests[i].fn() != 0)
            return 1;
        printf("EFI_PARSER_%s=PASS\n", tests[i].name);
    }
    return 0;
}
