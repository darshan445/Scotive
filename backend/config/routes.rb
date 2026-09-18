Rails.application.routes.draw do
  get "up" => "rails/health#show", as: :rails_health_check
  get "/api/health", to: "api/health#show"

  devise_for :users, skip: :all

  namespace :api do
    namespace :v1 do
      namespace :auth do
        post "sign-up", to: "registrations#create"
        post "sign-in", to: "sessions#create"
        delete "sign-out", to: "sessions#destroy"
        get "me", to: "me#show"
        post "forgot-password", to: "passwords#create"
        post "reset-password", to: "passwords#update"
      end
    end
  end
end
