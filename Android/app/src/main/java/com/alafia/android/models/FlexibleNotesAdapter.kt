package com.alafia.android.models

import com.google.gson.TypeAdapter
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import com.google.gson.stream.JsonWriter

/**
 * Reads `clinical_notes`, which arrives as EITHER a string or a list of note
 * records.
 *
 * On a completed flowsheet the backend sends a LIST — clinical notes are their
 * own append-only rows, not a column on the session. Against a plain
 * `String?` field Gson throws `Expected a string but was BEGIN_ARRAY`, the
 * whole session list fails to parse, and the screen shows "no sessions"
 * underneath a summary that counts them.
 *
 * CLAUDE.md §3aa twice over: the array shape is named there as a known
 * production failure, and an error must never be rendered as an empty state.
 *
 * The list form is flattened to the joined note text so the existing `String?`
 * call sites keep working; `clinicalNotesList` still carries the structured
 * records where a screen wants them.
 */
class FlexibleNotesAdapter : TypeAdapter<String?>() {

    override fun read(reader: JsonReader): String? = when (reader.peek()) {
        JsonToken.NULL -> {
            reader.nextNull(); null
        }
        JsonToken.STRING -> reader.nextString().ifEmpty { null }
        JsonToken.BEGIN_ARRAY -> {
            val texts = mutableListOf<String>()
            reader.beginArray()
            while (reader.hasNext()) {
                if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                    reader.beginObject()
                    while (reader.hasNext()) {
                        if (reader.nextName() == "note_text" && reader.peek() == JsonToken.STRING) {
                            reader.nextString().takeIf { it.isNotEmpty() }?.let(texts::add)
                        } else {
                            reader.skipValue()
                        }
                    }
                    reader.endObject()
                } else {
                    // A bare string in the array, or something unexpected.
                    if (reader.peek() == JsonToken.STRING) {
                        reader.nextString().takeIf { it.isNotEmpty() }?.let(texts::add)
                    } else {
                        reader.skipValue()
                    }
                }
            }
            reader.endArray()
            texts.joinToString("\n").ifEmpty { null }
        }
        else -> {
            // Unknown shape: skip rather than fail the WHOLE session list over
            // one field.
            reader.skipValue(); null
        }
    }

    override fun write(writer: JsonWriter, value: String?) {
        // Writes stay a plain string — that is what the create/update endpoint
        // expects. Only reads have to tolerate both shapes.
        if (value == null) writer.nullValue() else writer.value(value)
    }
}
