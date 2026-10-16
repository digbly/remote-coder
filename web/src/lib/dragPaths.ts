// Custom `dataTransfer` type carrying a project-relative path when a file or
// folder is dragged from the explorer into a terminal. A dedicated type keeps
// this drag distinct from plain text and from files dragged in from the OS.
export const PROJECT_PATH_MIME = 'application/x-remote-coder-path'
