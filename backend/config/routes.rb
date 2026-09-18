Rails.application.routes.draw do
  get "up" => "rails/health#show", as: :rails_health_check
  get "/api/health", to: "api/health#show"

  devise_for :users, skip: :all

  # Intuit app redirect URI is registered at /api/qbo/oauth/callback (see QBO_REDIRECT_URI).
  get "/api/qbo/oauth/callback", to: "api/v1/qbo/oauth#callback"
  post "/api/qbo/webhooks", to: "api/qbo/webhooks#create"

  namespace :api do
    namespace :v1 do
      namespace :auth do
        post "sign-up", to: "registrations#create"
        post "sign-in", to: "sessions#create"
        delete "sign-out", to: "sessions#destroy"
        get "me", to: "me#show"
        post "forgot-password", to: "passwords#create"
        post "reset-password", to: "passwords#update"
        delete "account", to: "accounts#destroy"
      end

      get "ledger", to: "ledger#show"
      get "clients", to: "clients#index"
      get "clients/:email", to: "clients#show", constraints: { email: /[^\/]+/ }
      get "invoices/:id/conversation", to: "invoices#conversation"
      get "invoices/:id/timeline", to: "invoices#timeline"
      post "invoices/:id/action", to: "invoices#action"
      post "invoices/:id/draft-chase", to: "invoices#draft_chase"
      post "invoices/:id/send-chase", to: "invoices#send_chase"
      get "sync", to: "sync#show"
      post "sync", to: "sync#create"

      get "settings", to: "settings#show"
      patch "settings", to: "settings#update"
      get "settings/timezones", to: "settings#timezones"
      get "digest/today", to: "digests#today"
      post "contact", to: "contacts#create"

      namespace :qbo do
        get "oauth/start", to: "oauth#start"
        get "oauth/callback", to: "oauth#callback"
        get "status", to: "connections#show"
        post "disconnect", to: "connections#destroy"
        post "import", to: "imports#create"
        get "pipeline-status", to: "pipelines#show"
        post "match-conversations", to: "pipelines#match"
      end

      namespace :gmail do
        get "oauth/start", to: "oauth#start"
        get "oauth/callback", to: "oauth#callback"
        get "status", to: "connections#show"
        post "disconnect", to: "connections#destroy"
        post "webhooks", to: "webhooks#create"
      end

      namespace :onboarding do
        get "state", to: "states#show"
        post "continue", to: "continues#create"
        post "qbo-step", to: "qbo_steps#create"
      end
    end

    namespace :admin do
      post "login", to: "sessions#create"
      get "me", to: "sessions#show"
      post "logout", to: "sessions#destroy"
      get "dashboard", to: "dashboards#show"
      get "users/:user_id/invoices", to: "user_invoices#index"
      get "contact-messages", to: "contact_messages#index"
      post "contact-messages/:id/read", to: "contact_messages#read"
    end
  end
end
