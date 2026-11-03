/* Exercise the actual patched kernel load_uefi.c with mock EFI services.
 * Native userspace only: never load modules or alter EFI variables.
 * This is an execution-path regression test, NOT proof of Secure Boot safety.
 */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define __init
#define late_initcall(fn)
#define UEFI_QUIRK_SKIP_CERT(v, m) .vendor = (v), .model = (m)
#define EFI_SHIM_LOCK_GUID 1
#define EFI_IMAGE_SECURITY_DATABASE_GUID 2
#define EFI_RT_SUPPORTED_GET_VARIABLE 0x10
#define EFI_SECURE_BOOT 12
#define EFI_NOT_FOUND 1UL
#define EFI_SUCCESS 0UL
#define EFI_BUFFER_TOO_SMALL 2UL
#define GFP_KERNEL 0
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
#define pr_warn(...) ((void)0)
#define kmalloc(sz, flags) malloc(sz)
#define kfree(ptr) free(ptr)

struct dmi_system_id { const char *vendor, *model; };
static const struct dmi_system_id *dmi_first_match(const struct dmi_system_id *t)
{ (void)t; return NULL; }

typedef int efi_guid_t;
typedef wchar_t efi_char16_t;
typedef unsigned long efi_status_t;
typedef void (*efi_element_handler_t)(void);
typedef efi_element_handler_t (*efi_handler_provider_t)(const efi_guid_t *);
struct efi_mokvar_table_entry {
    char name[256];
    unsigned long long data_size;
    unsigned char data[8];
};

static bool runtime_available, early_secureboot, integrity_secureboot;
static bool mok_present, mokx_present, moktrusted_present;
static int mokx_parse_error, mok_parse_error;
static int efi_calls, mok_calls, mokx_calls, mok_handler_calls;
static char load_order[8];

static bool efi_rt_services_supported(int features)
{ (void)features; return runtime_available; }
static bool efi_enabled(int feature)
{ (void)feature; return early_secureboot; }
static bool arch_get_secureboot(void)
{ return integrity_secureboot; }
static const char *efi_status_to_str(efi_status_t code)
{ (void)code; return "mock error"; }
static efi_status_t mock_get_variable(efi_char16_t *name, efi_guid_t *guid,
                                     void *attributes, unsigned long *size,
                                     void *data)
{
    (void)name; (void)guid; (void)attributes; (void)size; (void)data;
    efi_calls++;
    return EFI_NOT_FOUND;
}
static struct {
    efi_status_t (*get_variable)(efi_char16_t *, efi_guid_t *, void *,
                                 unsigned long *, void *);
} efi = { mock_get_variable };

static struct efi_mokvar_table_entry mok_rt, mokx_rt, mok_trusted_rt;
static struct efi_mokvar_table_entry *efi_mokvar_entry_find(const char *name)
{
    if (!strcmp(name, "MokListRT"))
        return mok_present ? &mok_rt : NULL;
    if (!strcmp(name, "MokListXRT"))
        return mokx_present ? &mokx_rt : NULL;
    if (!strcmp(name, "MokListTrustedRT"))
        return moktrusted_present ? &mok_trusted_rt : NULL;
    return NULL;
}
static void dummy(void) { }
static efi_element_handler_t get_handler_for_db(const efi_guid_t *type)
{ (void)type; return dummy; }
static efi_element_handler_t get_handler_for_mok(const efi_guid_t *type)
{ (void)type; mok_handler_calls++; return dummy; }
static efi_element_handler_t get_handler_for_dbx(const efi_guid_t *type)
{ (void)type; return dummy; }
static int parse_efi_signature_list(const char *source, const void *data,
                                    size_t size, efi_handler_provider_t provider)
{
    (void)data; (void)size;
    const efi_guid_t x509 = 1;
    (void)provider(&x509);
    if (strstr(source, "MokListXRT")) {
        load_order[mokx_calls + mok_calls] = 'X';
        mokx_calls++;
        return mokx_parse_error;
    }
    if (strstr(source, "MokListRT")) {
        load_order[mokx_calls + mok_calls] = 'M';
        mok_calls++;
        return mok_parse_error;
    }
    return 0;
}

/* This resolves to patched load_uefi.c in a disposable temporary tree. */
#include "security/integrity/platform_certs/load_uefi.c"

#define ASSERT_EQ(value, expect) do {                                         \
    if ((value) != (expect)) {                                               \
        fprintf(stderr, "%s:%d %s expected %ld got %ld\n", __func__,       \
                __LINE__, #value, (long)(expect), (long)(value));            \
        return 1;                                                            \
    }                                                                        \
} while (0)
#define ASSERT_ORDER(want) do {                                              \
    if (strcmp(load_order, want)) {                                          \
        fprintf(stderr, "%s order expected %s got %s\n", __func__,          \
                want, load_order);                                           \
        return 1;                                                            \
    }                                                                        \
} while (0)

static void reset_mock(void)
{
    runtime_available = false;
    early_secureboot = true;
    integrity_secureboot = false;
    mok_present = mokx_present = moktrusted_present = true;
    mokx_parse_error = mok_parse_error = 0;
    efi_calls = mok_calls = mokx_calls = mok_handler_calls = 0;
    memset(load_order, 0, sizeof(load_order));
    memset(&mok_rt, 0, sizeof(mok_rt));
    memset(&mokx_rt, 0, sizeof(mokx_rt));
}
static int case_insecure_blocks_all(void)
{
    reset_mock();
    early_secureboot = false;
    ASSERT_EQ(load_uefi_certs(), 0);
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(mokx_calls, 0);
    ASSERT_EQ(efi_calls, 0);
    return 0;
}
static int case_offline_import_and_order(void)
{
    reset_mock();
    ASSERT_EQ(load_uefi_certs(), 0);
    ASSERT_ORDER("XM");
    ASSERT_EQ(mok_handler_calls, 1);
    ASSERT_EQ(efi_calls, 0);
    return 0;
}
static int case_offline_mokx_invalid_blocks_mok(void)
{
    reset_mock();
    mokx_parse_error = -22;
    ASSERT_EQ(load_uefi_certs(), -22);
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(mokx_calls, 1);
    ASSERT_EQ(efi_calls, 0);
    return 0;
}
static int case_offline_missing_mokx_blocks_mok(void)
{
    reset_mock();
    mokx_present = false;
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(load_uefi_certs(), -22);
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(efi_calls, 0);
    return 0;
}
static int case_offline_missing_moktrusted_blocks_mok(void)
{
    reset_mock();
    moktrusted_present = false;
    ASSERT_EQ(load_uefi_certs(), -22);
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(mokx_calls, 0);
    ASSERT_EQ(efi_calls, 0);
    return 0;
}
static int case_offline_missing_mok_no_import(void)
{
    reset_mock();
    mok_present = false;
    ASSERT_EQ(load_uefi_certs(), 0);
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(mokx_calls, 1);
    ASSERT_EQ(efi_calls, 0);
    return 0;
}
static int case_online_integrity_unknown_blocks_mok(void)
{
    reset_mock();
    runtime_available = true;
    ASSERT_EQ(load_uefi_certs(), 0);
    ASSERT_EQ(mok_calls, 0);
    ASSERT_EQ(mokx_calls, 0);
    ASSERT_EQ(efi_calls > 0, true);
    return 0;
}
static int case_online_secure_imports_mok(void)
{
    reset_mock();
    runtime_available = true;
    integrity_secureboot = true;
    ASSERT_EQ(load_uefi_certs(), 0);
    ASSERT_ORDER("XM");
    ASSERT_EQ(efi_calls > 0, true);
    return 0;
}
int main(void)
{
    int (*const cases[])(void) = {
        case_insecure_blocks_all,
        case_offline_import_and_order,
        case_offline_mokx_invalid_blocks_mok,
        case_offline_missing_mokx_blocks_mok,
        case_offline_missing_moktrusted_blocks_mok,
        case_offline_missing_mok_no_import,
        case_online_integrity_unknown_blocks_mok,
        case_online_secure_imports_mok,
    };
    unsigned int i;
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        if (cases[i]()) return 1;
        printf("MOCK_CASE_%u=PASS\n", i + 1);
    }
    return 0;
}
