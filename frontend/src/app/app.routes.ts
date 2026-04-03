import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
  },
  {
    path: 'entities',
    loadComponent: () => import('./features/entities/entity-tree.component').then(m => m.EntityTreeComponent),
  },
  {
    path: 'accounts/:slug',
    loadComponent: () => import('./features/accounts/account-detail.component').then(m => m.AccountDetailComponent),
  },
  {
    path: 'ledger/:accountId',
    loadComponent: () => import('./features/ledger/ledger-browser.component').then(m => m.LedgerBrowserComponent),
  },
  {
    path: 'compliance',
    loadComponent: () => import('./features/compliance/compliance-view.component').then(m => m.ComplianceViewComponent),
  },
  {
    path: 'deficiency',
    loadComponent: () => import('./features/deficiency/deficiency-view.component').then(m => m.DeficiencyViewComponent),
  },
  {
    path: 'resources',
    loadComponent: () => import('./features/resources/resources-view.component').then(m => m.ResourcesViewComponent),
  },
  {
    path: 'discovery',
    loadComponent: () => import('./features/discovery/discovery.component').then(m => m.DiscoveryComponent),
  },
  {
    path: 'feedback',
    loadComponent: () => import('./features/feedback/feedback-list.component').then(m => m.FeedbackListComponent),
  },
  { path: '**', redirectTo: '', pathMatch: 'full' },
];
