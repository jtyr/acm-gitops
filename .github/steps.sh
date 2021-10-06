#!/bin/bash


# Fail on any error
set -e


# Global vars
ACM_SCRIPT='./.github/acm/acm.py -v'
ACM_METADATA_BRANCH=${ACM_METADATA_BRANCH:-master}


# Show usage message for this script
function usage() {
    EXIT=${1:-0}

    echo "Usage: $0 <workflow> <step>"
    echo ''
    echo 'Workflows and their steps:'
    echo ' * pr'
    echo '    - apps_changed'
    echo '    - single_app_check'
    echo '    - check_parameters_exist'
    echo '    - check_promotion_exist'
    echo '    - res_validation'
    echo '    - validate_placements'
    echo ' * merge'
    echo '    - tag_app'
    echo '    - tag_create_push'
    echo ' * tag'
    echo '    - info_get'
    echo '    - prev_env_tag_exists'
    echo '    - deployment_generate_deploy'
    echo '    - deployment_next_env'
    echo '    - deployment_promote'

    exit "$EXIT"
}


# Print formatted message
function msg() {
    TYPE="$1"
    TEXT="$2"
    EXIT="$3"

    if [[ $GITHUB_ACTIONS == true ]]; then
        # Use GitHub message commands when running inside GitHub Action
        if [[ $TYPE == 'E' ]]; then
            TYPE='::error::'
        elif [[ $TYPE == 'W' ]]; then
            TYPE='::warning::'
        elif [[ $TYPE == 'I' ]]; then
            TYPE='::notice::'
        else
            TYPE='::debug::'
        fi

        echo "$TYPE$TEXT"
    else
        # Message format for local run
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $TYPE: $TEXT"
    fi

    if [[ -n $EXIT ]]; then
        exit "$EXIT"
    fi
}


# Show error and exit when the workflow/step is unknown
function input_error() {
    TYPE="$1"

    if [[ $TYPE == 'workflow' ]]; then
        msg 'E' "Unknown workflow '$WORKFLOW'"
    else
        msg 'E' "Unknown workflow '$STEP'"
    fi

    usage 1
}


###########
### PR ###
        #

# Check if PR contains changes for apps and return number and in case of single
# app changed also its name
function pr_apps_changed() {
    APP_NAME=$(git diff "origin/$ACM_METADATA_BRANCH" --name-only | grep -Ev '^\.github' | grep -Po '^[a-z0-9-]+/' | sort -u)
    NUM_CHANGED=$(echo "$APP_NAME" | grep -Evc '^$' || true)

    echo "::set-output name=number::$NUM_CHANGED"

    if [[ $NUM_CHANGED == 1 ]]; then
        echo "::set-output name=app_name::${APP_NAME:0:-1}"
    else
        echo '::set-output name=app_name::'
    fi
}


# Check if only one app changed and show error if more than one changed
function pr_single_app_check() {
    # Check required env vars
    if [[ -z $NUM_CHANGED ]]; then
        msg 'E' 'No NUM_CHANGED defined' 1
    fi

    if [[ $NUM_CHANGED != 1 ]]; then
        msg 'E' "There must be change to exactly one application (found changes: $NUM_CHANGED)." 1
    else
        msg 'I' 'All good'
    fi
}

# Check if parameters.yaml file exists
function pr_check_parameters_exist() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    fi

    if [[ -f $APP_NAME/parameters.yaml ]]; then
        msg 'I' 'The "parameters.yaml" file exists'
    else
        msg 'E' 'The "parameters.yaml" file does not exist'
    fi
}

# Check if promotion.yaml file exists
function pr_check_promotion_exist() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    fi

    if [[ -f $APP_NAME/promotion.yaml ]]; then
        msg 'I' 'The "promotion.yaml" file exists'
    else
        msg 'E' 'The "promotion.yaml" file does not exist'
    fi
}

# Validate resource
function pr_res_validation() {
    msg 'I' 'TODO: Validating resource...'
}


# Validate if placement-rules exist for all placements in the promotion.yaml file
function pr_validate_placements() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    elif [[ -z $GITHUB_WORKSPACE ]]; then
        msg 'E' 'No GITHUB_WORKSPACE defined' 1
    fi

    export ACM_RELEASE_PATH="$GITHUB_WORKSPACE/.release"

    $ACM_SCRIPT validate placements "$APP_NAME"
}


##############
### Merge ###
           #

# Get app name from the last merged code
function merge_tag_app() {
    # Get the app name from changes done since the last tag
    LAST_TAG=$(git tag | sort -V | tail -n1 | grep -E '^.+$')
    APP_NAME=$(git diff "$LAST_TAG" --name-only | grep -Ev '^\.github' | grep -Po '^[a-z0-9-]+/' | sort -u | sed 's,/$,,')

    echo "::set-output name=app_name::$APP_NAME"
}


# Create and push new tag
function merge_tag_create_push() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    elif [[ -z $VERSION ]]; then
        msg 'E' 'No VERSION defined' 1
    fi

    # Get first env name
    FIRST_ENV=$($ACM_SCRIPT get first-env "$APP_NAME")

    if [[ -z $FIRST_ENV ]]; then
        msg 'E' 'Failed to get first-env' 1
    fi

    # Get the next free tag (max 300 iterations without version change)
    for REL in {1..1000}; do
        TAG="$APP_NAME-$VERSION-$REL-$FIRST_ENV"

        TAG_EXISTS=$(git tag -l "$TAG" | wc -l)

        if [[ $TAG_EXISTS -eq '0' ]]; then
            break
        fi
    done

    if [[ $TAG_EXISTS != '0' ]]; then
        msg 'E' 'Failed to get new tag' 1
    fi

    git tag "$TAG"
    git push --tags
}


############
### Tag ###
         #

# Get app info from the tag reference
function tag_info_get() {
    # Check required env vars
    if [[ -z $GITHUB_REF ]]; then
        msg 'E' 'No GITHUB_REF defined' 1
    fi

    # TAG
    TAG=${GITHUB_REF:10}

    # Extract env name
    ENV=${TAG##*-}

    # Extract app name
    APP_NO_ENV=${TAG%-*}
    APP_NO_REL=${APP_NO_ENV%-*}
    APP=${APP_NO_REL%-*}

    # Extract version
    VERSION=${APP_NO_ENV:${#APP}+1}

    echo "::set-output name=app_name::$APP"
    echo "::set-output name=app_version::$VERSION"
    echo "::set-output name=env_name::$ENV"
    echo "::set-output name=tag::$TAG"
}


# Check that tag from previous env exists (unless we are in the first env)
function tag_prev_env_tag_exists() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    elif [[ -z $APP_VERSION ]]; then
        msg 'E' 'No APP_VERSION defined' 1
    elif [[ -z $ENV_NAME ]]; then
        msg 'E' 'No ENV_NAME defined' 1
    fi

    FIRST_ENV=$($ACM_SCRIPT get first-env "$APP_NAME")

    if [[ "$FIRST_ENV" == "$ENV_NAME" ]]; then
        msg 'I' 'First env - nothing to do.'

        return
    fi

    PREV_ENV=$($ACM_SCRIPT get prev-env "$APP_NAME" "$ENV_NAME")
    TAG="$APP_NAME-$APP_VERSION-$PREV_ENV-success"
    TAG_EXISTS=$(git tag -l "$TAG" | wc -l)

    if [[ $TAG_EXISTS == 0 ]]; then
        msg 'E' "Tag '$TAG' does not exist" 1
    else
        msg 'I' "Tag '$TAG' exists"
    fi
}


# Generate ACM resource and deploy them
function tag_deployment_generate_deploy() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    elif [[ -z $ENV_NAME ]]; then
        msg 'E' 'No ENV_NAME defined' 1
    elif [[ -z $GITHUB_WORKSPACE ]]; then
        msg 'E' 'No GITHUB_WORKSPACE defined' 1
    fi

    export ACM_RELEASE_PATH="$GITHUB_WORKSPACE/.release"

    for ZONES in $($ACM_SCRIPT get zones "$APP_NAME" "$ENV_NAME"); do
        IFS=',' read -ra ZONE <<< "$ZONES"

        for Z in "${ZONE[@]}"; do
            # Generate
            $ACM_SCRIPT generate "$APP_NAME" "$ENV_NAME" "$Z"
        done

        if [[ $(git -C "$ACM_RELEASE_PATH" status --porcelain | wc -l) -gt 0 ]]; then
            # Commit and push
            git config --global user.email 'gitops@finastra.com'
            git config --global user.name 'GitHub Action'
            git -C "$ACM_RELEASE_PATH" add -A
            git -C "$ACM_RELEASE_PATH" commit -am "Changes from $TAG - zone: $ZONES"
            git -C "$ACM_RELEASE_PATH" push

            msg 'I' 'TODO: Waiting for deployment status...'

            # TODO: Tag failure
            #git tag "$TAG-$Z-fail"
            #git tag "$TAG-fail"
            #git push --tags
            #echo '::error::Deployment failed'
            #exit 1

            # Tag success/failure
            for Z in "${ZONE[@]}"; do
                git tag "$TAG-$Z-success"
            done
        fi
    done

    # Tag successful env deployment
    git tag "$TAG-success"

    # Push all success tags
    git push --tags
}


# Get name of the next env for promotion
function tag_deployment_next_env() {
    # Check required env vars
    if [[ -z $APP_NAME ]]; then
        msg 'E' 'No APP_NAME defined' 1
    elif [[ -z $ENV_NAME ]]; then
        msg 'E' 'No ENV_NAME defined' 1
    fi

    NAME=$($ACM_SCRIPT get next-env "$APP_NAME" "$ENV_NAME")

    echo "::set-output name=env_name::$NAME"
}


# Create and push tag to trigger the next step of the promotion
function tag_deployment_promote() {
    # Check required env vars
    if [[ -z $TAG ]]; then
        msg 'E' 'No TAG defined' 1
    fi

    if [[ -n $NEXT_ENV ]]; then
        # Create tag to trigger next env deployment
        git tag "${TAG%-*}-$NEXT_ENV"
        git push --tags
    else
        msg 'I' 'End of promotion'
    fi
}


# Input parameters
WORKFLOW="$1"
STEP="$2"

# Print usage message
if [[ $WORKFLOW == '-h' || $WORKFLOW == '--help' ]]; then
    usage
fi

# Verify input parameters
if [[ -z $WORKFLOW ]]; then
    msg 'E' 'No workflow specified'

    usage 1
fi

if [[ -z $STEP ]]; then
    msg 'E' 'No step specified'

    usage 1
fi

# Decide what to do
if [[ $WORKFLOW == 'pr' ]]; then
    if [[ $STEP == 'apps_changed' ]]; then
        pr_apps_changed
    elif [[ $STEP == 'single_app_check' ]]; then
        pr_single_app_check
    elif [[ $STEP == 'check_parameters_exist' ]]; then
        pr_check_parameters_exist
    elif [[ $STEP == 'check_promotion_exist' ]]; then
        pr_check_promotion_exist
    elif [[ $STEP == 'res_validation' ]]; then
        pr_res_validation
    elif [[ $STEP == 'validate_placements' ]]; then
        pr_validate_placements
    else
        input_error step
    fi
elif [[ $WORKFLOW == 'merge' ]]; then
    if [[ $STEP == 'tag_app' ]]; then
        merge_tag_app
    elif [[ $STEP == 'tag_create_push' ]]; then
        merge_tag_create_push
    else
        input_error step
    fi
elif [[ $WORKFLOW == 'tag' ]]; then
    if [[ $STEP == 'info_get' ]]; then
        tag_info_get
    elif [[ $STEP == 'prev_env_tag_exists' ]]; then
        tag_prev_env_tag_exists
    elif [[ $STEP == 'deployment_generate_deploy' ]]; then
        tag_deployment_generate_deploy
    elif [[ $STEP == 'deployment_next_env' ]]; then
        tag_deployment_next_env
    elif [[ $STEP == 'deployment_promote' ]]; then
        tag_deployment_promote
    else
        input_error step
    fi
else
    input_error workflow
fi
