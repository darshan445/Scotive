Rails.application.routes.draw do
  get "up" => "rails/health#show", as: :rails_health_check
  get "/api/health", to: "api/health#show"

  devise_for :users, skip: :all
  devise_scope :user do
    post "/api/auth/sign_up", to: "api/auth/registrations#create"
    post "/api/auth/sign_in", to: "api/auth/sessions#create"
    delete "/api/auth/sign_out", to: "api/auth/sessions#destroy"
  end
end
