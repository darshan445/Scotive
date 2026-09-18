# Interactor Pattern — Developer Manual

## Overview

Interactors are plain Ruby command objects that encapsulate a single use case or
pipeline step.  Each one exposes a class-level `.execute` method and returns an
`OpenStruct` so callers always have a consistent shape to work with:

```ruby
result = MyInteractor.execute(some_arg)
result.success?  # => true / false
result.data      # present when success? is true  (last value in the block)
result.errors    # present when success? is false (the exception message)
```

---

## Generate a new interactor

```bash
# Simple (top-level class)
bin/rails generate interactor MyClassName

# Namespaced (creates module folder automatically)
bin/rails generate interactor Payments::ChargeCard
```

Each invocation creates:

| File | Purpose |
|------|---------|
| `app/interactors/<name>.rb` | The interactor class |
| `spec/interactors/<name>_spec.rb` | Skeleton RSpec file |

---

## Anatomy of an interactor

```ruby
# frozen_string_literal: true

class DoSomething
  include ExecuteMethodHelper   # provides execute_log_and_return_open_struct
  include LogHelper             # provides raise_string_error, validate_result, ...

  # 1. Class-level entry point — always call this from outside.
  def self.execute(user_id:, order_id:)
    new(user_id: user_id, order_id: order_id).execute
  end

  # 2. Store dependencies in ivars.
  def initialize(user_id:, order_id:)
    @user_id  = user_id
    @order_id = order_id
  end

  # 3. execute wraps work in the helper block.
  def execute
    execute_log_and_return_open_struct do
      user  = find_user!
      order = find_order!
      process(user, order)   # last expression becomes result.data — never return inside execute
    end
  end

  private

  attr_reader :user_id, :order_id

  def find_user!
    User.find(user_id)
  rescue ActiveRecord::RecordNotFound
    raise_string_error("User #{user_id} not found")
  end

  def find_order!
    Order.find(order_id)
  rescue ActiveRecord::RecordNotFound
    raise_string_error("Order #{order_id} not found")
  end

  def process(user, order)
    # ... your business logic ...
    order
  end
end
```

---

## Key helpers (LogHelper)

| Method | When to use |
|--------|-------------|
| `raise_string_error("msg")` | Raise a user-friendly error anywhere; logs it and raises StandardError. |
| `validate_result(Other.execute(...))` | Call a child interactor and re-raise its error if it failed. |
| `validate_result_without_raising_error(result)` | Same, but does not raise (use for non-fatal flows). |
| `handle_open_struct_response(result)` | Controller convenience: returns .data on success, .errors on failure. |

---

## Composing interactors

```ruby
def execute
  execute_log_and_return_open_struct do
    token  = validate_result(Auth::GetToken.execute(user_id: user_id)).data
    result = validate_result(Api::PostPayload.execute(token: token, payload: payload)).data
    result
  end
end
```

If either child interactor fails, validate_result raises, the wrapper catches it,
and the parent returns { success?: false, errors: "child error message" } automatically.

---

## Controller usage

```ruby
def create
  result = DoSomething.execute(user_id: current_user.id, order_id: params[:order_id])

  if result.success?
    render json: result.data, status: :created
  else
    render json: { error: result.errors }, status: :unprocessable_entity
  end
end
```

---

## File layout

```
app/
  interactors/
    concerns/
      log_helper.rb             <- LogHelper module
      execute_method_helper.rb  <- ExecuteMethodHelper module
    my_feature/
      do_something.rb           <- interactors grouped by domain
      do_something_else.rb
spec/
  interactors/
    my_feature/
      do_something_spec.rb
lib/
  generators/
    interactor/
      interactor_generator.rb
      interactor_generator_manual.md   <- this file
      templates/
        interactor_template.rb.erb
        interactor_spec_template.rb.erb
```

---

*Pattern originally developed for Mother Goose (mg-backend).*
