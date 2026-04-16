# Pruner — locked forward-design constraints (Phase 2+)

This document records **design locks** for Pruner after Phase 1. It does **not** expand Phase 1 scope. Phase 1 only establishes the Pruner lane (`pruner_jobs`, `pruner.*` job kinds, workers, routing, honest empty surface) and must **not** introduce media-server integrations, combined TV/Movies behavior, or a single global “the server” config.

---

## Two-axis separation (locked)

### 1. TV and Movies remain independent everywhere Pruner operates

Including:

- rules  
- schedules  
- previews  
- live delete passes  
- caps / limits  
- activity / result surfaces  

One axis must **not** block or interfere with the other.

### 2. Media server connections / instances remain independent

Including:

- Emby  
- Jellyfin  
- Plex (first-class alongside Emby and Jellyfin — not a deferred afterthought)  
- multiple instances of the same provider if supported  

One server instance must **not** implicitly share runtime behavior with another. Concretely:

- no shared preview / delete state  
- no shared schedule behavior  
- no shared limits / caps  
- no shared result surfaces  
- no cross-instance interference  

### 3. No single global media server config

Future Pruner design must **not** assume one global media server configuration. The ownership boundary must be:

- **per server instance**  
- with **TV and Movies separated inside that instance**  

### 4. Phase 1 unchanged

These rules apply to **Phase 2 and later** only. Phase 1 must not hard-code Emby-only paths, combined TV/Movies keys, or a global media-server singleton that would contradict this model.

---

## Phase 1 compatibility (implementation note)

Phase 1 work (lane rename, `trimmer_jobs` removal, `pruner_jobs` creation, removal of the old non-Pruner vertical, docs/nav copy) introduces **no** structures that require a single combined TV/Movies scope or a single global server. New code and copy should **avoid** wording or APIs that imply otherwise, so the lane stays compatible with this two-axis separation when product features land.

**Integration scope lock:** future Pruner server support is **Emby + Jellyfin + Plex** together — design must not assume Emby-only or “Plex later” sequencing; see ADR-0007 Pruner lane forward-design pointer.
