"""Patch only the generated ESPHome 2026.10.1 API source, never the installation."""

HEADER = '#include "api_connection.h"\n'
DECLARATION = (
    "namespace esphome::single_fan { const char *ha_entity_name(uint32_t key); }\n"
)
ORIGINAL = """  if (entity->has_own_name()) {
    msg.name = entity->get_name();
  }
"""
REPLACEMENT = """  // single_fan: retain legacy object IDs while translating display names.
  char object_id_buf[OBJECT_ID_MAX_LEN];
  msg.object_id = entity->get_object_id_to(object_id_buf);

  if (entity->has_own_name()) {
    msg.name = entity->get_name();
  }
  if (const char *name = single_fan::ha_entity_name(msg.key)) {
    msg.name = StringRef(name);
  }
"""


def patch_source(source):
    # Fail closed when the pinned upstream implementation changes or is partly patched.
    if (
        source.count(DECLARATION) == 1
        and source.count(REPLACEMENT) == 1
        and source.count(ORIGINAL) == 1
    ):
        return source
    if (
        source.count(HEADER) != 1
        or source.count(ORIGINAL) != 1
        or DECLARATION in source
        or REPLACEMENT in source
    ):
        raise RuntimeError(
            "Unexpected ESPHome API source; review the Chinese entity name patch before building"
        )
    return source.replace(HEADER, HEADER + DECLARATION).replace(ORIGINAL, REPLACEMENT)
