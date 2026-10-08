const memoryTypes: Record<string, string> = {
  fact: 'Fait',
  preference: 'Préférence',
  constraint: 'Contrainte',
  decision: 'Décision',
  goal: 'Objectif',
  interest: 'Intérêt',
  habit: 'Habitude',
};

export function memoryTypeLabel(type: string): string {
  return memoryTypes[type] ?? 'Souvenir';
}

export function memoryOriginLabel(origin: string | null): string {
  switch (origin) {
    case 'explicit':
      return 'confirmée par vous';
    case 'inferred':
      return 'déduite';
    case 'observed':
      return 'observée';
    default:
      return 'non précisée';
  }
}

export function memorySourceLabel(sourceType: string, sourceRunId: string | null): string {
  if (sourceType === 'correction') return 'correction manuelle';
  if (sourceType === 'assistant_message') return 'échange avec l’assistant';
  if (sourceRunId) return 'capture traitée';
  if (sourceType === 'capture') return 'pensée enregistrée';
  return 'non précisée';
}

export function formatMemoryDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'date indisponible' : date.toLocaleDateString('fr-FR');
}
