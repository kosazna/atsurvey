// Project lifecycle strings (security plan phase 4; deep-merged by lib/i18n.ts).
const lifecycleEl = {
  life: {
    tabs: { active: "Ενεργά", archived: "Αρχειοθετημένα", trash: "Κάδος" },
    archive: "Αρχειοθέτηση",
    archived: "Το έργο αρχειοθετήθηκε. Δεν μετράει στο όριο έργων.",
    unarchive: "Επαναφορά",
    unarchived: "Το έργο επανήλθε στα ενεργά.",
    duplicate: "Αντίγραφο",
    duplicateName: "{{name}} (αντίγραφο)",
    duplicated: "Δημιουργήθηκε αντίγραφο.",
    trashed: "Το έργο μεταφέρθηκε στον κάδο για {{days}} ημέρες.",
    undo: "Αναίρεση",
    restore: "Επαναφορά",
    restored: "Το έργο επανήλθε.",
    deleteForever: "Οριστική διαγραφή",
    deleteForeverConfirm: "Οριστική διαγραφή του «{{name}}» με όλους τους υπολογισμούς και τα αρχεία; Δεν αναιρείται.",
    deletedForever: "Το έργο διαγράφηκε οριστικά.",
    purgeIn: "διαγράφεται σε {{days}} ημέρες",
    emptyArchived: "Κανένα αρχειοθετημένο έργο.",
    emptyTrash: "Ο κάδος είναι άδειος. Τα έργα μένουν εδώ 30 ημέρες πριν διαγραφούν οριστικά.",
    trashHint: "Τα διαγραμμένα έργα μένουν 30 ημέρες στον κάδο και μπορούν να επανέλθουν.",
    copySettings: "Ρυθμίσεις από",
    copySettingsNone: "Προεπιλογές",
    files: {
      title: "Πρωτότυπα αρχεία",
      text: "Τα αρχεία οργάνων όπως εισήχθησαν, με το αποτύπωμα SHA-256 τους.",
      download: "Λήψη",
      empty: "Δεν έχουν εισαχθεί αρχεία σε αυτό το έργο.",
    },
    runs: {
      label: "Όνομα",
      labelPlaceholder: "π.χ. Τελική λύση",
      saved: "Αποθηκεύτηκε.",
      delete: "Διαγραφή υπολογισμού",
      deleted: "Ο υπολογισμός διαγράφηκε.",
    },
  },
};

export type LifecycleMessages = typeof lifecycleEl;
export default lifecycleEl;
