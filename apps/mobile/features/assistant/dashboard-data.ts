export const dashboardTags = ['school', 'work', 'errands', 'family'] as const;

export type DashboardTag = (typeof dashboardTags)[number];

export const dashboardTagLabels: Record<DashboardTag, string> = {
  school: 'École',
  work: 'Travail',
  errands: 'Courses',
  family: 'Famille',
};

export type DashboardTask = {
  id: string;
  title: string;
  detail: string;
  timing: string;
  tone: 'now' | 'soon' | 'later';
  tags: DashboardTag[];
  completed: boolean;
};

export type MentalNote = {
  id: string;
  text: string;
  context: string;
  tags: DashboardTag[];
};

export type GroceryItem = {
  id: string;
  label: string;
  checked: boolean;
};

export const previewGroceryItems: GroceryItem[] = [
  { id: 'pasta', label: 'Pâtes complètes', checked: false },
  { id: 'eggs', label: 'Œufs', checked: false },
  { id: 'courgettes', label: 'Courgettes', checked: false },
  { id: 'chickpeas', label: 'Pois chiches', checked: true },
  { id: 'basil', label: 'Basilic', checked: false },
];

export const trainingTypes = ['renforcement', 'course', 'mobilite'] as const;

export type TrainingType = (typeof trainingTypes)[number];

export const trainingTypeLabels: Record<TrainingType, string> = {
  renforcement: 'Renforcement',
  course: 'Course',
  mobilite: 'Mobilité',
};

export type TrainingSession = {
  id: string;
  label: string;
  type: TrainingType;
  timing: string;
  completed: boolean;
};

export const previewTrainingSessions: TrainingSession[] = [
  {
    id: 'mobility',
    label: 'Mobilité douce',
    type: 'mobilite',
    timing: 'Lundi · 20 min',
    completed: true,
  },
  {
    id: 'running',
    label: 'Course légère',
    type: 'course',
    timing: 'Jeudi · 30 min',
    completed: false,
  },
];

// Données temporaires : elles rendent le parcours visible sans prétendre
// provenir de l'assistant ni être enregistrées dans le compte.
export const previewTasks: DashboardTask[] = [
  {
    id: 'dentist',
    title: 'Confirmer le rendez-vous chez le dentiste',
    detail: 'Appeler le cabinet pour trouver un créneau pour Léa.',
    timing: 'Aujourd’hui · 17 h 30',
    tone: 'now',
    tags: ['school', 'family'],
    completed: false,
  },
  {
    id: 'sunday-lunch',
    title: 'Répondre pour le déjeuner de dimanche',
    detail: 'Prévenir Mamie du nombre de personnes.',
    timing: 'Aujourd’hui',
    tone: 'soon',
    tags: ['family'],
    completed: false,
  },
  {
    id: 'groceries',
    title: 'Préparer la liste de courses',
    detail: 'Ajouter ce qui manque avant demain matin.',
    timing: 'Demain',
    tone: 'later',
    tags: ['errands'],
    completed: false,
  },
];

export const previewMentalNotes: MentalNote[] = [
  {
    id: 'gift',
    text: 'Cadeau d’anniversaire de Léo',
    context: 'Avant le 22 septembre',
    tags: ['family'],
  },
  {
    id: 'insurance',
    text: 'Envoyer le justificatif à la mutuelle',
    context: 'Cette semaine',
    tags: ['errands'],
  },
  {
    id: 'weekend',
    text: 'Idée de sortie pour samedi',
    context: 'À décider en famille',
    tags: ['family'],
  },
];
