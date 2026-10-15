export function createTaskService(repository) {
  const fail = (statusCode, code, message) => {
    const error = new Error(message);
    error.statusCode = statusCode;
    error.code = code;
    throw error;
  };
  const requireId = (id) => {
    if (typeof id !== 'string' || !id.trim()) fail(400, 'INVALID_TASK_INPUT', 'id must be a non-empty string.');
  };
  return {
    list: () => repository.list(),
    create: ({ title }) => {
      if (typeof title !== 'string' || !title.trim()) fail(400, 'INVALID_TASK_INPUT', 'title must be a non-empty string.');
      const id = globalThis.crypto.randomUUID();
      const task = { id, title: title.trim(), completed: false };
      return repository.create(task);
    },
    update: async (id, changes) => {
      requireId(id);
      if (!changes || typeof changes.completed !== 'boolean') fail(400, 'INVALID_TASK_INPUT', 'completed must be a boolean.');
      if (!(await repository.findById(id))) fail(404, 'TASK_NOT_FOUND', 'Task not found.');
      return repository.update(id, { completed: changes.completed });
    },
    remove: async (id) => {
      requireId(id);
      if (!(await repository.findById(id))) fail(404, 'TASK_NOT_FOUND', 'Task not found.');
      return repository.remove(id);
    },
  };
}
